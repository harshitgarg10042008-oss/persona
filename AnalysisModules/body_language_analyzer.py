"""
Web-optimized body language analysis module for Django backend
Analyzes posture, eye contact, and gestures from webcam snapshots

REFACTORED: all local MediaPipe detectors (pose / face mesh / hands) and
OpenCV removed. Analysis now uses the Groq hosted vision model to score
posture, eye contact, face orientation, and gestures from the image in a
single JSON-structured response. The public API (analyze_body_language /
analyze_body_language_base64 and return shapes) is unchanged so existing
callers keep working.
"""

import base64
import io
import json
import logging
import os
import re
from typing import Dict, Optional

from PIL import Image

logger = logging.getLogger(__name__)

VISION_MODEL = os.getenv('GROQ_VISION_MODEL', 'llama-3.2-90b-vision-preview')


def _get_api_key() -> Optional[str]:
    try:
        from django.conf import settings
        configured = getattr(settings, 'GROQ_API_KEY', None)
        if configured:
            return configured
    except Exception:
        pass
    return os.getenv('GROQ_API_KEY')


def _groq_vision(image_bytes: bytes, prompt: str, timeout: int = 60) -> Optional[str]:
    """Send an image to the Groq hosted vision model and return the text."""
    api_key = _get_api_key()
    if not api_key:
        logger.warning('Groq API key not configured for body language analysis')
        return None
    try:
        from groq import Groq
    except ImportError:  # pragma: no cover - runtime fallback
        logger.warning('groq SDK missing for body language analysis')
        return None

    b64 = base64.b64encode(image_bytes).decode('ascii')
    try:
        client = Groq(api_key=api_key)
        chat = client.chat.completions.create(
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': prompt},
                    {'type': 'image_url',
                     'image_url': {'url': f'data:image/jpeg;base64,{b64}'}},
                ],
            }],
            model=VISION_MODEL,
            temperature=0.2,
            timeout=timeout,
            max_tokens=1024,
        )
        return chat.choices[0].message.content or ''
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning('Groq vision request failed: %s', exc)
        return None


def _parse_json_payload(text: str) -> Optional[Dict]:
    """Best-effort extraction of a JSON object from the model response."""
    if not text:
        return None
    cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    for candidate in (cleaned, re.search(r'\{.*\}', cleaned, flags=re.S)):
        if candidate:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    return None


class WebBodyLanguageAnalyzer:
    """Web-optimized body language analyzer for Django assessment system (Groq vision)"""

    def __init__(self):
        self.is_initialized = True  # stateless Groq client; nothing to load
        self.analysis_config = {
            'posture_weight': 0.35,
            'eye_contact_weight': 0.25,
            'gesture_weight': 0.20,
            'face_orientation_weight': 0.20,
        }

    def initialize_detectors(self):
        """No-op compatibility shim (Groq needs no local detectors)."""
        return True

    def analyze_image(self, image_data: bytes) -> Dict:
        """
        Main analysis function for web use.

        Args:
            image_data: Raw image bytes from webcam

        Returns:
            Dict with analysis results and scores
        """
        try:
            if len(image_data) < 256:
                return self._error_result('Image data too small to analyze')

            # Normalize to JPEG and downscale large webcam frames
            image = Image.open(io.BytesIO(image_data))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            image.thumbnail((768, 768))
            buf = io.BytesIO()
            image.save(buf, format='JPEG', quality=75)
            normalized = buf.getvalue()

            prompt = """
You are evaluating a candidate's body language from a webcam snapshot taken \
during a video interview. The person is seated and facing the camera.

Analyze the image and score:
1. posture_score: how upright, straight, and professional their posture is (shoulders level, spine straight, not slouching or leaning excessively)
2. eye_contact_score: how directly they are facing the camera (gaze toward camera vs looking away/down/sideways)
3. face_orientation_score: how forward-facing and centered their head is
4. gesture_score: whether hand movements and positioning appear natural and controlled (not fidgeting, waving excessively, or blocking the face)

Return ONLY valid JSON with these keys:
{
  "posture_score": <0-1 float>,
  "eye_contact_score": <0-1 float>,
  "face_orientation_score": <0-1 float>,
  "gesture_score": <0-1 float>,
  "feedback": ["<one short specific feedback line>", ...],
  "recommendations": ["<one short actionable recommendation>", ...]
}
"""
            payload = _parse_json_payload(_groq_vision(normalized, prompt))

            results = {
                'overall_score': 0.0,
                'posture_score': 0.0,
                'eye_contact_score': 0.0,
                'gesture_score': 0.0,
                'face_orientation_score': 0.0,
                'details': {},
                'feedback': [],
                'recommendations': [],
                'confidence': 0.0,
                'timestamp': None,
            }

            if payload:
                for key in ('posture_score', 'eye_contact_score',
                            'gesture_score', 'face_orientation_score'):
                    try:
                        results[key] = float(payload.get(key, 0.0))
                    except (TypeError, ValueError):
                        pass
                results['details']['groq_analysis'] = payload
                results['details']['detected'] = True
                results['feedback'] = list(payload.get('feedback', [])) or []
                results['recommendations'] = list(payload.get('recommendations', [])) or []
                results['confidence'] = 0.9
            else:
                # Vision API unavailable: neutral fallback that does not block the flow
                results['details']['error'] = 'Groq vision analysis unavailable; neutral scores returned'
                results['details']['detected'] = False
                for key in ('posture_score', 'eye_contact_score',
                            'gesture_score', 'face_orientation_score'):
                    results[key] = 0.5
                results['feedback'] = ['Body language analysis unavailable this session.']
                results['recommendations'] = []
                results['confidence'] = 0.3

            self._generate_feedback(results)
            results['overall_score'] = self._calculate_overall_score(results)
            return results

        except Exception as exc:
            logger.error('Error in body language analysis: %s', exc)
            return self._error_result(str(exc))

    def _generate_feedback(self, results: Dict):
        """Generate supplemental feedback when model feedback is thin."""
        feedback = list(results.get('feedback', []) or [])
        recommendations = list(results.get('recommendations', []) or [])
        if results.get('posture_score', 0) < 0.6:
            recommendations.append('Sit up straight with shoulders back and aligned.')
        if results.get('eye_contact_score', 0) < 0.5:
            recommendations.append('Try to look more directly at the camera.')
        if not feedback:
            overall = results.get('overall_score', 0)
            if overall >= 0.8:
                feedback.append('Overall excellent body language for a professional setting!')
            elif overall >= 0.6:
                feedback.append('Good body language with room for minor improvements.')
            else:
                feedback.append('Focus on improving your overall body language and presence.')
        results['feedback'] = feedback[:5]
        results['recommendations'] = recommendations[:5]

    def _calculate_overall_score(self, results: Dict) -> float:
        """Calculate weighted overall body language score."""
        try:
            config = self.analysis_config
            weighted = (
                results.get('posture_score', 0) * config['posture_weight'] +
                results.get('eye_contact_score', 0) * config['eye_contact_weight'] +
                results.get('gesture_score', 0) * config['gesture_weight'] +
                results.get('face_orientation_score', 0) * config['face_orientation_weight']
            )
            confidence = results.get('confidence', 0.5)
            return min(weighted * (0.5 + confidence * 0.5), 1.0)
        except Exception:
            return 0.5

    def _error_result(self, error_message: str) -> Dict:
        return {
            'overall_score': 0.0,
            'error': error_message,
            'feedback': ['Analysis failed due to technical error'],
            'recommendations': ['Please ensure good lighting and camera positioning'],
            'confidence': 0.0,
            'timestamp': None,
        }

    def analyze_base64_image(self, base64_data: str) -> Dict:
        """Convenience method for base64 image data from web frontend"""
        try:
            if ',' in base64_data:
                base64_data = base64_data.split(',')[1]
            image_bytes = base64.b64decode(base64_data)
            return self.analyze_image(image_bytes)
        except Exception as exc:
            logger.error('Error processing base64 image: %s', exc)
            return self._error_result(f'Invalid image data: {exc}')


# Singleton instance for web use
body_language_analyzer = WebBodyLanguageAnalyzer()


def analyze_body_language(image_data):
    """Main function for Django views to call"""
    return body_language_analyzer.analyze_image(image_data)


def analyze_body_language_base64(base64_data):
    """Function for analyzing base64 images from web frontend"""
    return body_language_analyzer.analyze_base64_image(base64_data)
