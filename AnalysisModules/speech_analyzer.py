"""
Web-optimized speech analysis module for Django backend
Analyzes speech fluency, pronunciation, and content relevance

REFACTORED: all heavy local dependencies (openai-whisper, librosa,
SpeechRecognition, textblob, nltk) removed. Transcription now uses the
Groq hosted whisper-large-v3 endpoint; fluency, formality, content, and
confidence scoring use a single structured Groq chat-completions prompt.
The public API (analyze_speech / quick_transcribe / analyze_voice_confidence
and their return shapes) is unchanged so existing callers keep working.
"""

import io
import json
import logging
import os
import re
import tempfile
import wave
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Groq dependency is optional at import time; analysis falls back to the
# standardized error result when the SDK is missing or the API key is unset.
try:
    from groq import Groq
except ImportError:  # pragma: no cover - runtime fallback
    Groq = None


def _get_api_key() -> Optional[str]:
    try:
        from django.conf import settings
        configured = getattr(settings, 'GROQ_API_KEY', None)
        if configured:
            return configured
    except Exception:
        pass
    return os.getenv('GROQ_API_KEY')


def _transcribe_groq(audio_bytes: bytes) -> Dict:
    """Transcribe audio bytes using Groq's hosted whisper-large-v3."""
    api_key = _get_api_key()
    if not api_key or Groq is None:
        raise RuntimeError('Groq API key not configured or groq SDK missing')

    with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as f:
        f.write(audio_bytes)
        path = f.name

    try:
        client = Groq(api_key=api_key)
        with open(path, 'rb') as audio_file:
            result = client.audio.transcriptions.create(
                model='whisper-large-v3',
                file=audio_file,
                response_format='verbose_json',
                temperature=0.0,
                language='en',
            )
        text = (result.text or '').strip()
        words = re.findall(r'[A-Za-z0-9\'-]+', text)
        return {
            'text': text,
            'word_count': len(words),
            'language': getattr(result, 'language', 'en') or 'en',
            'segments': getattr(result, 'segments', None) or [],
            'confidence': 0.9,
        }
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# LLM-based metric scoring
# ---------------------------------------------------------------------------

_SPEECH_PROMPT = """\
You are a professional speech and communication coach evaluating a recorded \
interview answer. Score the candidate on the five dimensions below, each on a \
0-1 scale (two decimals).

Question: {question_text}

Transcript: {transcript}

Evaluate:
1. fluency_score: words per minute, presence of filler words (um, uh, like, you know), unnatural pauses, and sentence flow.
2. pronunciation_score: clarity and articulation of words, slurring, mumbling, and how confidently words are enunciated.
3. content_score: relevance and depth of the answer to the question, completeness, and use of concrete examples.
4. formality_score: professionalism and formality of language (avoid slang, contractions, and overly casual expressions).
5. confidence_score: overall vocal confidence (filler word frequency, hesitations, steady pace, assertiveness).

Return ONLY valid JSON with these keys:
{{
  "fluency_score": <0-1 float>,
  "pronunciation_score": <0-1 float>,
  "content_score": <0-1 float>,
  "formality_score": <0-1 float>,
  "confidence_score": <0-1 float>,
  "words_per_minute": <number>,
  "filler_count": <integer>,
  "feedback": ["<one short specific feedback line>", ...],
  "recommendations": ["<one short actionable recommendation>", ...]
}}
"""


def _score_with_groq(transcript: str, question_text: str = '') -> Optional[Dict]:
    """Ask Groq to score the transcript on the five speech dimensions."""
    api_key = _get_api_key()
    if not api_key or Groq is None:
        return None
    try:
        client = Groq(api_key=api_key)
        model = 'llama-3.3-70b-versatile'
        try:
            from django.conf import settings
            configured = getattr(settings, 'GROQ_MODEL', None)
            if configured:
                model = configured.strip() or model
        except Exception:
            pass
        chat_completion = client.chat.completions.create(
            messages=[{
                'role': 'user',
                'content': _SPEECH_PROMPT.format(
                    question_text=question_text or '(question text unavailable)',
                    transcript=transcript,
                ),
            }],
            model=model,
            temperature=0.2,
            timeout=60,
        )
        text = chat_completion.choices[0].message.content or ''
        # Strip markdown fences
        cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        payload = json.loads(cleaned)
        return {
            'fluency_score': float(payload.get('fluency_score', 0.5)),
            'pronunciation_score': float(payload.get('pronunciation_score', 0.5)),
            'content_score': float(payload.get('content_score', 0.5)),
            'formality_score': float(payload.get('formality_score', 0.5)),
            'confidence_score': float(payload.get('confidence_score', 0.5)),
            'words_per_minute': float(payload.get('words_per_minute', 0)),
            'filler_count': int(payload.get('filler_count', 0)),
            'feedback': list(payload.get('feedback', [])) or [],
            'recommendations': list(payload.get('recommendations', [])) or [],
        }
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning('Groq speech scoring failed: %s', exc)
        return None


class WebSpeechAnalyzer:
    """Web-optimized speech analyzer for Django assessment system (Groq-based)"""

    def __init__(self):
        self.is_initialized = True  # Groq is stateless; nothing to load
        self.analysis_config = {
            'fluency_weight': 0.25,
            'pronunciation_weight': 0.20,
            'content_weight': 0.25,
            'formality_weight': 0.15,
            'confidence_weight': 0.15,
            'min_words_per_minute': 120,
            'max_words_per_minute': 180,
            'min_response_length': 10,
            'optimal_response_length': 50,
        }

    def initialize_models(self):
        """No-op compatibility shim (Groq needs no local models)."""
        return True

    # -----------------------------------------------------------------------
    # Main analysis entry point
    # -----------------------------------------------------------------------
    def analyze_audio(self, audio_data: bytes, question_text: str = '',
                      response_duration: float = None) -> Dict:
        """
        Main analysis function for web use.

        Args:
            audio_data: Raw audio bytes (WebM as recorded by the browser)
            question_text: The question that was asked
            response_duration: Duration of response in seconds (informational)

        Returns:
            Dict with analysis results and scores
        """
        results = {
            'overall_score': 0.0,
            'fluency_score': 0.0,
            'pronunciation_score': 0.0,
            'content_score': 0.0,
            'formality_score': 0.0,
            'confidence_score': 0.0,
            'transcription': '',
            'word_count': 0,
            'speaking_rate': 0.0,
            'details': {},
            'feedback': [],
            'recommendations': [],
            'analysis_confidence': 0.0,
            'timestamp': datetime.now().isoformat(),
        }

        if len(audio_data) < 1024:
            return self._error_result(f'Audio too small ({len(audio_data)} bytes)')

        # 1. Transcribe via Groq hosted whisper
        try:
            transcription_results = _transcribe_groq(audio_data)
        except Exception as exc:
            logger.error('Transcription failed: %s', exc)
            return self._error_result(f'Transcription failed: {exc}')

        results['transcription'] = transcription_results['text']
        results['word_count'] = transcription_results['word_count']
        results['details']['transcription'] = transcription_results

        if results['word_count'] == 0:
            return self._error_result('No speech detected in audio')

        # 2. Estimate speaking rate from word count / duration
        duration = response_duration or response_duration
        if duration and duration > 0:
            results['speaking_rate'] = round((results['word_count'] / duration) * 60, 1)
        else:
            segments = transcription_results.get('segments') or []
            if segments:
                last_seg_end = max((s.get('end', 0) or 0) for s in segments)
                if last_seg_end > 0:
                    results['speaking_rate'] = round((results['word_count'] / last_seg_end) * 60, 1)

        # 3. Score all five dimensions with a structured Groq LLM prompt
        scores = _score_with_groq(transcription_results['text'], question_text)
        if scores:
            results['fluency_score'] = scores['fluency_score']
            results['pronunciation_score'] = scores['pronunciation_score']
            results['content_score'] = scores['content_score']
            results['formality_score'] = scores['formality_score']
            results['confidence_score'] = scores['confidence_score']
            results['speaking_rate'] = scores.get('words_per_minute', results['speaking_rate'])
            results['details']['llm_scores'] = scores
            results['feedback'] = scores.get('feedback', [])
            results['recommendations'] = scores.get('recommendations', [])
        else:
            # LLM fallback unavailable: derive deterministic proxy scores from
            # the transcript so the pipeline still returns usable numbers.
            results['fluency_score'] = self._proxy_fluency(transcription_results['text'])
            results['pronunciation_score'] = min(transcription_results.get('confidence', 0.9), 1.0)
            results['content_score'] = self._proxy_content(transcription_results['text'], question_text)
            results['formality_score'] = self._proxy_formality(transcription_results['text'])
            results['confidence_score'] = self._proxy_confidence(transcription_results['text'])

        results['analysis_confidence'] = self._calculate_analysis_confidence(results['details'])
        if not results['feedback']:
            self._generate_feedback(results)

        results['overall_score'] = self._calculate_overall_score(results)
        return results

    # -----------------------------------------------------------------------
    # Deterministic proxy scorers (used only when the Groq LLM is unavailable)
    # -----------------------------------------------------------------------
    @staticmethod
    def _tokenize(text):
        return re.findall(r'[a-z\']+', text.lower())

    def _proxy_fluency(self, text: str) -> float:
        words = self._tokenize(text)
        filler_count = sum(
            1 for w in words
            if w in {'um', 'uh', 'like', 'you', 'know', 'actually', 'literally'}
        )
        ratio = filler_count / len(words) if words else 0
        return max(0.0, min(1.0, 1 - ratio * 5))

    def _proxy_content(self, text: str, question_text: str = '') -> float:
        words = self._tokenize(text)
        if len(words) >= 50:
            length_score = 1.0
        elif len(words) >= 10:
            length_score = len(words) / 50
        else:
            length_score = max(0.0, len(words) / 10 * 0.5)
        relevance = 0.7
        if question_text:
            q_words = set(self._tokenize(question_text)) - {'what', 'how', 'why', 'tell', 'me', 'about', 'the', 'a', 'an', 'your', 'you'}
            r_words = set(words)
            if q_words:
                relevance = min(len(q_words & r_words) / len(q_words) * 2, 1.0)
        return length_score * 0.6 + relevance * 0.4

    def _proxy_formality(self, text: str) -> float:
        words = self._tokenize(text)
        informal = {'yeah', 'yep', 'nope', 'gonna', 'wanna', 'gotta', 'kinda', 'sorta', 'awesome', 'cool', 'stuff'}
        ratio = sum(1 for w in words if w in informal) / len(words) if words else 0
        return max(0.0, min(1.0, 1 - ratio * 3))

    def _proxy_confidence(self, text: str) -> float:
        return self._proxy_fluency(text)

    # -----------------------------------------------------------------------
    # Legacy helpers kept for backward compatibility
    # -----------------------------------------------------------------------
    def _calculate_analysis_confidence(self, details: Dict) -> float:
        factors = []
        transcription = details.get('transcription', {})
        factors.append(float(transcription.get('confidence', 0.5)))
        factors.append(min(transcription.get('word_count', 0) / 30, 1.0))
        if 'llm_scores' in details:
            factors.append(0.9)
        return sum(factors) / len(factors) if factors else 0.3

    def _generate_feedback(self, results: Dict):
        feedback, recommendations = [], []
        overall = results.get('overall_score', 0)
        if overall >= 0.8:
            feedback.append('Excellent speech delivery and communication skills!')
        elif overall >= 0.6:
            feedback.append('Good communication with some areas for improvement.')
        else:
            feedback.append('Your speech delivery could be improved for professional settings.')
        if results.get('fluency_score', 1) < 0.6:
            recommendations.append('Practice reducing filler words (um, uh, like).')
        if results.get('content_score', 1) < 0.6:
            if results.get('word_count', 0) < 20:
                recommendations.append('Provide more detailed responses to questions.')
            recommendations.append('Use more professional vocabulary to strengthen your answers.')
        if results.get('formality_score', 1) < 0.6:
            recommendations.append('Use more formal language appropriate for professional settings.')
        if results.get('confidence_score', 1) < 0.6:
            recommendations.append('Practice speaking with more confidence and steady pace.')
        results['feedback'] = feedback
        results['recommendations'] = recommendations

    def _calculate_overall_score(self, results: Dict) -> float:
        try:
            config = self.analysis_config
            weighted = (
                results.get('fluency_score', 0) * config['fluency_weight'] +
                results.get('pronunciation_score', 0) * config['pronunciation_weight'] +
                results.get('content_score', 0) * config['content_weight'] +
                results.get('formality_score', 0) * config['formality_weight'] +
                results.get('confidence_score', 0) * config['confidence_weight']
            )
            conf = results.get('analysis_confidence', 0.5)
            return min(weighted * (0.3 + conf * 0.7), 1.0)
        except Exception:
            return 0.5

    @staticmethod
    def _sanitize_numpy_types(obj):
        # Groq results are native Python types; keep the shim for callers.
        if hasattr(obj, 'item') and hasattr(obj, 'dtype'):
            return obj.item()
        elif hasattr(obj, 'tolist'):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: WebSpeechAnalyzer._sanitize_numpy_types(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [WebSpeechAnalyzer._sanitize_numpy_types(i) for i in obj]
        elif isinstance(obj, tuple):
            return tuple(WebSpeechAnalyzer._sanitize_numpy_types(i) for i in obj)
        return obj

    def _error_result(self, error_message: str) -> Dict:
        return {
            'overall_score': 0.0,
            'error': error_message,
            'transcription': '',
            'word_count': 0,
            'feedback': ['Speech analysis failed due to technical error'],
            'recommendations': ['Please ensure clear audio recording and try again'],
            'analysis_confidence': 0.0,
            'timestamp': datetime.now().isoformat(),
        }

    # -----------------------------------------------------------------------
    # Voice confidence analysis (0-10 scale, Groq-based)
    # -----------------------------------------------------------------------
    def analyze_voice_confidence(self, audio_bytes: bytes, transcription: str = '') -> Dict:
        """
        Analyze vocal confidence from the audio.
        Returns confidence score (0-10 scale) and human-readable observations.
        """
        try:
            transcript = transcription or ''
            if not transcript:
                transcript = _transcribe_groq(audio_bytes).get('text', '')

            prompt = f"""
You are a communication coach assessing vocal confidence from an interview response.

Transcript: {transcript}

Assess the speaker's confidence based on filler-word usage, hesitations,
assertiveness, pace, and overall delivery. Return ONLY valid JSON:
{{
  "score": <0-10 float>,
  "observations": ["<one short observation>", "..."],
  "metrics": {{"filler_count": <int>, "words": <int>}}
}}
"""
            api_key = _get_api_key()
            if api_key and Groq is not None:
                client = Groq(api_key=api_key)
                model = 'llama-3.3-70b-versatile'
                try:
                    from django.conf import settings
                    configured = getattr(settings, 'GROQ_MODEL', None)
                    if configured:
                        model = configured.strip() or model
                except Exception:
                    pass
                chat = client.chat.completions.create(
                    messages=[{'role': 'user', 'content': prompt}],
                    model=model,
                    temperature=0.2,
                    timeout=60,
                )
                text = chat.choices[0].message.content or ''
                cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
                cleaned = re.sub(r'\s*```$', '', cleaned)
                payload = json.loads(cleaned)
                return {
                    'score': round(float(payload.get('score', 5.0)), 1),
                    'observations': payload.get('observations', []),
                    'metrics': payload.get('metrics', {}),
                    'detailed_scores': {},
                }

            # LLM unavailable: deterministic fallback
            words = self._tokenize(transcript)
            filler_count = sum(1 for w in words if w in {'um', 'uh', 'like'})
            filler_ratio = filler_count / len(words) if words else 0
            observations = []
            if filler_count > 5:
                observations.append(f"High filler word count ({filler_count}) — practice reducing 'um', 'uh', 'like'")
            elif filler_count <= 2 and words:
                observations.append('Minimal filler words — shows good preparation and confidence')
            score = max(0.0, min(10.0, (1 - filler_ratio * 4) * 8))
            return {
                'score': round(score, 1),
                'observations': observations or ['Confidence assessment available once Groq LLM is configured.'],
                'metrics': {'filler_count': filler_count, 'words': len(words)},
                'detailed_scores': {},
            }
        except Exception as exc:
            logger.error('Voice confidence analysis failed: %s', exc)
            return {
                'score': 0.0,
                'observations': [f'Analysis failed: {exc}'],
                'metrics': {'error': str(exc)},
                'detailed_scores': {},
            }


# Singleton instance for web use
speech_analyzer = WebSpeechAnalyzer()


def analyze_speech(audio_data, question_text='', response_duration=None):
    """Main function for Django views to call"""
    results = speech_analyzer.analyze_audio(audio_data, question_text, response_duration)
    return speech_analyzer._sanitize_numpy_types(results)


def quick_transcribe(audio_data):
    """Quick transcription function using Groq hosted whisper."""
    try:
        result = _transcribe_groq(audio_data)
        return result.get('text', '')
    except Exception as exc:
        logger.error('Quick transcription failed: %s', exc)
        return ''


def analyze_voice_confidence(audio_data, transcription=''):
    """
    Analyze vocal confidence from audio data.

    Args:
        audio_data: Raw audio bytes
        transcription: Transcribed text (optional)

    Returns:
        Dict with confidence score (0-10), observations, and detailed metrics
    """
    results = speech_analyzer.analyze_voice_confidence(audio_data, transcription)
    return speech_analyzer._sanitize_numpy_types(results)
