"""
Web-optimized attire analysis module for Django backend
Analyzes professional attire from webcam snapshots

REFACTORED: all heavy local models (CLIP, BLIP, ViT via torch/torchvision/
transformers) removed. Analysis now uses the Groq hosted vision model, which
describes the candidate's attire and returns structured professionalism scores
in JSON. The public API (analyze_attire / analyze_attire_base64 and return
shapes) is unchanged so existing callers keep working.
"""

import base64
import io
import json
import logging
import os
import re
from typing import Dict, List, Optional

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
        logger.warning('Groq API key not configured for vision analysis')
        return None
    try:
        from groq import Groq
    except ImportError:  # pragma: no cover - runtime fallback
        logger.warning('groq SDK missing for vision analysis')
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
    # Try full text first; fall back to the first {...} span.
    for candidate in (cleaned, re.search(r'\{.*\}', cleaned, flags=re.S)):
        if candidate:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    return None


class WebAttireAnalyzer:
    """Web-optimized attire analyzer for Django assessment system (Groq vision)"""

    PROFESSIONAL_STANDARDS = {
        'formal_business': 'formal business (suit, blazer, dress shirt, tie, blouse or professional dress)',
        'business_casual': 'business casual (blazer or cardigan, collared shirt, blouse, neat trousers)',
        'smart_casual': 'smart casual (neat shirt, blouse, sweater, or smart top)',
    }

    def __init__(self):
        self.is_initialized = True  # stateless Groq client; nothing to load

    def initialize_models(self):
        """No-op compatibility shim (Groq needs no local models)."""
        return True

    def analyze_image(self, image_data: bytes,
                      assessment_type: str = 'formal_business') -> Dict:
        """
        Main analysis function for web use.

        Args:
            image_data: Raw image bytes from webcam/upload
            assessment_type: 'formal_business', 'business_casual', or 'smart_casual'

        Returns:
            Dict with analysis results and scores
        """
        try:
            if len(image_data) < 256:
                return self._error_result('Image data too small to analyze')

            # Normalize to JPEG (Groq vision prefers common image formats)
            image = Image.open(io.BytesIO(image_data))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            # Downscale large webcam frames to keep the payload reasonable
            image.thumbnail((768, 768))
            buf = io.BytesIO()
            image.save(buf, format='JPEG', quality=75)
            normalized = buf.getvalue()

            standard = self.PROFESSIONAL_STANDARDS.get(
                assessment_type,
                'formal business (suit, blazer, dress shirt, tie, blouse or professional dress)',
            )

            prompt = f"""
You are evaluating a candidate's attire for a video interview. The expected dress code for this interview is: {standard}.

Analyze the visible clothing and overall professional appearance in the image.

Return ONLY valid JSON with these keys:
{{
  "professionalism_score": <0-1 float>,
  "appropriateness_score": <0-1 float>,
  "grooming_score": <0-1 float>,
  "color_coordination_score": <0-1 float>,
  "fit_score": <0-1 float>,
  "description": "<one sentence describing what the person is wearing>",
  "feedback": ["<one short specific feedback line>", ...],
  "recommendations": ["<one short actionable recommendation>", ...]
}}
"""
            payload = _parse_json_payload(_groq_vision(normalized, prompt))

            results = {
                'overall_score': 0.0,
                'professionalism_score': 0.0,
                'appropriateness_score': 0.0,
                'grooming_score': 0.0,
                'color_coordination_score': 0.0,
                'fit_score': 0.0,
                'details': {},
                'feedback': [],
                'recommendations': [],
                'assessment_type': assessment_type,
                'timestamp': None,
            }

            if payload:
                for key in ('professionalism_score', 'appropriateness_score',
                            'grooming_score', 'color_coordination_score', 'fit_score'):
                    try:
                        results[key] = float(payload.get(key, 0.0))
                    except (TypeError, ValueError):
                        pass
                results['details']['description'] = payload.get('description', '')
                results['details']['groq_analysis'] = payload
                results['feedback'] = list(payload.get('feedback', [])) or []
                results['recommendations'] = list(payload.get('recommendations', [])) or []
            else:
                # Vision API unavailable: neutral fallback that does not block the flow
                results['details']['error'] = 'Groq vision analysis unavailable; neutral scores returned'
                results['details']['description'] = ''
                results['feedback'] = ['Attire analysis unavailable this session.']
                results['recommendations'] = []

            if not results['feedback']:
                self._generate_feedback(results, assessment_type)
            results['overall_score'] = self._calculate_overall_score(
                results, assessment_type)
            return results

        except Exception as exc:
            logger.error('Error in attire analysis: %s', exc)
            return self._error_result(str(exc))

    def _generate_feedback(self, results: Dict, assessment_type: str):
        """Fallback generic feedback when the model returns no feedback lines."""
        feedback, recommendations = [], []
        overall = results.get('overall_score', 0)
        if overall >= 0.8:
            feedback.append('Excellent professional appearance!')
        elif overall >= 0.6:
            feedback.append('Good professional appearance with room for improvement.')
        else:
            feedback.append('Your attire could be more professional for this setting.')
        standards = self.PROFESSIONAL_STANDARDS.get(assessment_type, '')
        if standards:
            recommendations.append(
                f'For {assessment_type.replace("_", " ")} settings, align with: {standards}')
        results['feedback'] = feedback
        results['recommendations'] = recommendations

    def _calculate_overall_score(self, results: Dict,
                                 assessment_type: str) -> float:
        """Calculate weighted overall score."""
        try:
            weights = {
                'professionalism_score': 0.4,
                'color_coordination_score': 0.2,
                'appropriateness_score': 0.2,
                'grooming_score': 0.1,
                'fit_score': 0.1,
            }
            type_weight = 0.8  # neutral default when local standards aren't used
            weighted, total = 0.0, 0.0
            for component, weight in weights.items():
                value = results.get(component)
                if value is not None:
                    weighted += float(value or 0.0) * weight
                    total += weight
            if total > 0:
                return min((weighted / total) * type_weight, 1.0)
            return 0.5
        except Exception:
            return 0.5

    def _error_result(self, error_message: str) -> Dict:
        return {
            'overall_score': 0.0,
            'error': error_message,
            'feedback': ['Analysis failed due to technical error'],
            'recommendations': ['Please try again or contact support'],
            'timestamp': None,
        }

    def analyze_base64_image(self, base64_data: str,
                             assessment_type: str = 'formal_business') -> Dict:
        """Convenience method for base64 image data from web frontend"""
        try:
            if ',' in base64_data:
                base64_data = base64_data.split(',')[1]
            image_bytes = base64.b64decode(base64_data)
            return self.analyze_image(image_bytes, assessment_type)
        except Exception as exc:
            logger.error('Error processing base64 image: %s', exc)
            return self._error_result(f'Invalid image data: {exc}')


# Singleton instance for web use
attire_analyzer = WebAttireAnalyzer()


def analyze_attire(image_data, assessment_type='formal_business'):
    """Main function for Django views to call"""
    return attire_analyzer.analyze_image(image_data, assessment_type)


def analyze_attire_base64(base64_data, assessment_type='formal_business'):
    """Function for analyzing base64 images from web frontend"""
    return attire_analyzer.analyze_base64_image(base64_data, assessment_type)
