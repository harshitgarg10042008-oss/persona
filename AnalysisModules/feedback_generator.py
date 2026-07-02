import json
import logging
import os
import re
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - runtime fallback
    genai = None


def _get_api_key() -> Optional[str]:
    configured_key = getattr(settings, 'GEMINI_API_KEY', None)
    if configured_key:
        return configured_key
    return os.getenv('GEMINI_API_KEY')


def _get_model_name() -> str:
    configured_model = getattr(settings, 'GEMINI_MODEL', None)
    if configured_model:
        return configured_model
    return os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')


def _call_gemini(prompt: str, timeout: int = 10):
    api_key = _get_api_key()
    if not api_key or genai is None:
        return None

    try:
        genai.configure(api_key=api_key)
        model_names = [
            _get_model_name().strip(),
            'gemini-2.0-flash',
            'gemini-2.0-flash-lite',
        ]
        model_names = [name for name in model_names if name]

        last_error = None
        for model_name in model_names:
            try:
                model = genai.GenerativeModel(model_name)
                try:
                    return model.generate_content(prompt, timeout=timeout)
                except TypeError:
                    try:
                        return model.generate_content(prompt, request_options={'timeout': timeout})
                    except TypeError:
                        return model.generate_content(prompt)
            except Exception as exc:  # pragma: no cover - defensive fallback
                last_error = exc

        if last_error is not None:
            raise last_error
        return None
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning('Gemini request failed: %s', exc)
        return None


def evaluate_answer_content(question_text: str, transcript: str, ideal_answer_points: str = None) -> dict:
    """Use Gemini to evaluate whether the candidate's answer was actually correct and relevant."""
    if not question_text or not transcript:
        return {
            'content_correctness_score': None,
            'explanation': 'Content evaluation unavailable',
        }

    prompt = f"""
You are evaluating an interview answer for correctness, relevance, and depth.
Question: {question_text}
Candidate answer: {transcript}
Ideal answer points: {ideal_answer_points or 'None provided'}

Score the answer on a 0-10 scale for content correctness, relevance, and depth.
Return ONLY valid JSON with two keys:
- content_correctness_score: a number between 0 and 10
- explanation: a brief 2-3 sentence explanation that mentions whether the answer actually addressed the question, whether the reasoning was sound, and whether the key aspects were covered.
"""

    try:
        response = _call_gemini(prompt)
        text = getattr(response, 'text', '') if response else ''
        if not text:
            raise ValueError('No Gemini response text')

        try:
            payload = json.loads(text)
            score = payload.get('content_correctness_score')
            explanation = payload.get('explanation') or 'Content evaluation unavailable'
        except json.JSONDecodeError:
            score_match = re.search(r'content_correctness_score[^0-9]*(\d+(?:\.\d+)?)', text, flags=re.IGNORECASE)
            score = float(score_match.group(1)) if score_match else None
            explanation = text.strip() or 'Content evaluation unavailable'

        if score is None:
            return {
                'content_correctness_score': None,
                'explanation': 'Content evaluation unavailable',
            }

        try:
            numeric_score = float(score)
        except (TypeError, ValueError):
            return {
                'content_correctness_score': None,
                'explanation': 'Content evaluation unavailable',
            }

        return {
            'content_correctness_score': max(0.0, min(10.0, numeric_score)),
            'explanation': explanation[:800] if explanation else 'Content evaluation unavailable',
        }
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning('Gemini content evaluation failed: %s', exc)
        return {
            'content_correctness_score': None,
            'explanation': 'Content evaluation unavailable',
        }


def generate_feedback_summary(scores: dict, per_question_evaluations: list) -> str:
    """Generate a concise, encouraging feedback paragraph for the full assessment."""
    overall_score = scores.get('overall_score')
    speaking_score = scores.get('speaking_score')
    body_language_score = scores.get('body_language_score')
    attire_score = scores.get('attire_score')

    evaluations_text = []
    for item in per_question_evaluations[:5]:
        question_text = item.get('question_text', 'Question')
        score = item.get('content_correctness_score')
        explanation = item.get('explanation', '')
        evaluations_text.append(f"- {question_text}: score={score}/10; {explanation}")

    prompt = f"""
You are writing feedback for an interview candidate.
Overall score: {overall_score}
Speaking score: {speaking_score}
Body language score: {body_language_score}
Attire score: {attire_score}

Per-question content evaluations:
{chr(10).join(evaluations_text) if evaluations_text else 'No per-question evaluations available.'}

Write a concise, encouraging 3-5 sentence paragraph that references both the delivery scores and whether the candidate's actual answers were substantively good. Include 1-2 concrete improvement areas.
"""

    try:
        response = _call_gemini(prompt)
        text = getattr(response, 'text', '') if response else ''
        if text:
            return text.strip()[:2000]
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning('Gemini feedback summary failed: %s', exc)

    return (
        'Feedback summary is currently unavailable, but your delivery and answer quality show clear potential. '
        'Focus on answering each question more directly and adding a few specific examples or reasoning points to strengthen your responses.'
    )
