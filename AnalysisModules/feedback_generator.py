import json
import logging
import os
import re
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    from groq import Groq
except ImportError:  # pragma: no cover - runtime fallback
    Groq = None


# ---------------------------------------------------------------------------
# Groq client helpers
# ---------------------------------------------------------------------------

def _get_api_key() -> Optional[str]:
    configured_key = getattr(settings, 'GROQ_API_KEY', None)
    if configured_key:
        return configured_key
    return os.getenv('GROQ_API_KEY')


def _get_model_name() -> str:
    configured_model = getattr(settings, 'GROQ_MODEL', None)
    if configured_model:
        return configured_model
    return os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')


def _call_groq(prompt: str, timeout: int = 30) -> Optional[str]:
    """
    Send *prompt* to the Groq chat completions API and return the response
    text, or None on any failure (missing key, import error, API error, etc.).
    """
    api_key = _get_api_key()
    if not api_key or Groq is None:
        return None

    try:
        client = Groq(api_key=api_key)
        model_name = _get_model_name().strip() or 'llama-3.3-70b-versatile'

        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "user", "content": prompt},
            ],
            model=model_name,
            timeout=timeout,
        )
        return chat_completion.choices[0].message.content or ''
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning('Groq request failed: %s', exc)
        return None


# ---------------------------------------------------------------------------
# Public functions — identical signatures and return shapes as before
# ---------------------------------------------------------------------------

def evaluate_answer_content(question_text: str, transcript: str, ideal_answer_points: str = None) -> dict:
    """Use Groq to evaluate whether the candidate's answer was actually correct and relevant."""
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
        text = _call_groq(prompt)
        if not text:
            raise ValueError('No Groq response text')

        # Strip markdown fences if the model added them
        cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        try:
            payload = json.loads(cleaned)
            score = payload.get('content_correctness_score')
            explanation = payload.get('explanation') or 'Content evaluation unavailable'
        except json.JSONDecodeError:
            score_match = re.search(r'content_correctness_score[^0-9]*(\d+(?:\.\d+)?)', cleaned, flags=re.IGNORECASE)
            score = float(score_match.group(1)) if score_match else None
            explanation = cleaned.strip() or 'Content evaluation unavailable'

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
        logger.warning('Groq content evaluation failed: %s', exc)
        return {
            'content_correctness_score': None,
            'explanation': 'Content evaluation unavailable',
        }


def generate_tailored_questions(resume_text: str, job_role: str, num_questions: int = 5) -> list[str]:
    """Generate a small set of tailored interview questions from resume text."""
    if not resume_text or not job_role:
        return []

    prompt = f"""
You are an expert interview question generator.
The resume text below describes a candidate's background, experience, projects, and skills.
The target role is: {job_role}

Resume text:
{resume_text}

Generate {num_questions} realistic interview questions specifically tailored to the candidate's actual experience. Avoid generic questions. If the resume mentions a project, technology, team, achievement, or responsibility, ask about those details directly.
Return ONLY a JSON array of strings, with no additional explanation.
"""

    try:
        text = _call_groq(prompt)
        if not text:
            raise ValueError('No Groq response')

        cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        try:
            questions = json.loads(cleaned)
            if isinstance(questions, list):
                return [str(q).strip() for q in questions if str(q).strip()][:num_questions]
        except json.JSONDecodeError:
            pass

        lines = [line.strip('-* \t\n') for line in cleaned.splitlines() if line.strip()]
        questions = [line for line in lines if len(line) > 10]
        return questions[:num_questions]

    except Exception as exc:
        logger.warning('Groq tailored question generation failed: %s', exc)
        return []


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
        text = _call_groq(prompt)
        if text:
            return text.strip()[:2000]
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning('Groq feedback summary failed: %s', exc)

    return (
        'Feedback summary is currently unavailable, but your delivery and answer quality show clear potential. '
        'Focus on answering each question more directly and adding a few specific examples or reasoning points to strengthen your responses.'
    )


# ---------------------------------------------------------------------------
# Improvement Roadmap — Steps 2, 3, 4
# ---------------------------------------------------------------------------

# Step 2 — single source of truth for level thresholds (change here only)
ROADMAP_LEVEL_THRESHOLDS = {
    'beginner': 5.0,     # overall_score < 5.0  → Beginner
    'intermediate': 7.5, # 5.0 ≤ overall_score ≤ 7.5 → Intermediate
    # > 7.5 → Advanced
}

# Target score used when computing gaps
ROADMAP_TARGET_SCORE = 8.0


def get_score_level(overall_score: float) -> str:
    """Map an overall_score (0-10) to a level label using ROADMAP_LEVEL_THRESHOLDS."""
    if overall_score is None:
        return 'Unknown'
    if overall_score < ROADMAP_LEVEL_THRESHOLDS['beginner']:
        return 'Beginner'
    if overall_score <= ROADMAP_LEVEL_THRESHOLDS['intermediate']:
        return 'Intermediate'
    return 'Advanced'


def detect_score_gaps(scores: dict, target: float = ROADMAP_TARGET_SCORE) -> list:
    """
    Compare confirmed sub-scores against the target and return a ranked list
    of gaps (largest gap first).

    Only operates on the three sub-scores that are reliably stored as float
    columns on IndividualAssessment: speaking_score, body_language_score,
    attire_score. Does NOT invent sub-metrics that don't exist in the DB.

    Returns:
        List of dicts [{'area': str, 'score': float, 'gap': float}, ...],
        sorted descending by gap (i.e. worst area first). Areas where score
        is None are omitted entirely.
    """
    # Confirmed DB-queryable sub-scores and their human-readable labels
    CONFIRMED_SUB_SCORES = {
        'speaking_score':       'Speaking & Delivery',
        'body_language_score':  'Body Language & Posture',
        'attire_score':         'Professional Attire',
    }

    gaps = []
    for field, label in CONFIRMED_SUB_SCORES.items():
        score = scores.get(field)
        if score is None:
            continue
        gap = max(0.0, target - float(score))
        gaps.append({'area': label, 'score': float(score), 'gap': gap})

    gaps.sort(key=lambda x: x['gap'], reverse=True)
    return gaps


def generate_improvement_roadmap(scores: dict, speech_details: dict = None) -> Optional[dict]:
    """
    Use Groq to produce a structured, actionable Improvement Roadmap.

    Args:
        scores: dict with keys overall_score, speaking_score,
                body_language_score, attire_score (all float or None).
        speech_details: optional dict from analysis_data['speech_analysis']
                        used to surface real filler-word data.

    Returns:
        A dict conforming to:
            {
              "level": str,               # Beginner / Intermediate / Advanced
              "current_score": float,     # overall_score
              "target_score": float,      # ROADMAP_TARGET_SCORE
              "action_items": [
                {
                  "area": str,            # e.g. "Speaking & Delivery"
                  "action": str,          # specific, measurable action
                  "why": str              # one-sentence rationale
                }, ...
              ]
            }
        Returns None when Groq is unavailable OR when no sub-scores exist
        (so the UI can show the "Analysis unavailable" pattern rather than
        a roadmap built on phantom data).
    """
    overall_score = scores.get('overall_score')

    # No roadmap if there's nothing real to work with
    if overall_score is None:
        return None

    gaps = detect_score_gaps(scores)
    if not gaps:
        return None  # No confirmed sub-scores at all — don't fabricate

    level = get_score_level(overall_score)

    # ------------------------------------------------------------------
    # Extract confirmed speech sub-metrics for richer action items.
    # These come from analysis_data['speech_analysis']['details']['fluency']
    # and are optional — if absent the roadmap still works.
    # ------------------------------------------------------------------
    fluency_details = {}
    if speech_details and isinstance(speech_details, dict):
        fluency_details = (
            speech_details
            .get('details', {})
            .get('fluency', {})
        )

    filler_count = fluency_details.get('filler_count')
    filler_ratio = fluency_details.get('filler_ratio')
    words_per_minute = fluency_details.get('words_per_minute')
    silence_ratio = fluency_details.get('silence_ratio')

    # Build a precise description of what speech data is available
    speech_data_lines = []
    if filler_count is not None:
        speech_data_lines.append(f"  - Filler word count: {filler_count} (ratio: {filler_ratio:.1%})")
    if words_per_minute is not None:
        speech_data_lines.append(f"  - Speaking rate: {words_per_minute:.0f} words per minute (target: 120-180 WPM)")
    if silence_ratio is not None:
        speech_data_lines.append(f"  - Silence/pause ratio: {silence_ratio:.1%} (optimal: ~20%)")

    # Gap summary for the prompt
    gap_lines = [
        f"  - {g['area']}: {g['score']:.1f}/10  (gap to target: {g['gap']:.1f} points)"
        for g in gaps
    ]

    prompt = f"""You are a professional interview coach generating a personalised improvement roadmap for a candidate.

CANDIDATE LEVEL: {level}
OVERALL SCORE: {overall_score:.1f}/10  (target: {ROADMAP_TARGET_SCORE}/10)

SUB-SCORE GAPS (largest gap = highest priority, all scores out of 10):
{chr(10).join(gap_lines)}

AVAILABLE SPEECH METRICS (confirmed from analysis):
{chr(10).join(speech_data_lines) if speech_data_lines else "  - No detailed speech metrics available for this session"}

CRITICAL CONSTRAINTS — you MUST follow these:
1. Only reference metrics that appear in the lists above. Do NOT invent:
   - Eye-contact percentage (not tracked — use "camera-facing orientation" if relevant)
   - Pupil/gaze direction
   - Individual pronunciation phoneme scores
   - Any metric not explicitly listed above
2. Action items must be SPECIFIC and MEASURABLE (e.g. "reduce filler words from {filler_count or 'N'} to under 5 per response", "complete 3 timed mock interviews at 140-160 WPM").
3. Generate between 4 and 6 action items total, prioritised by gap size.
4. Each action item must name the exact area it targets.

Return ONLY valid JSON (no markdown fences, no prose outside the JSON) matching this exact schema:
{{
  "level": "{level}",
  "current_score": {overall_score:.1f},
  "target_score": {ROADMAP_TARGET_SCORE},
  "action_items": [
    {{
      "area": "<area name matching one of the sub-score labels above, or 'Overall'>",
      "action": "<specific, measurable action sentence>",
      "why": "<one sentence explaining the impact>"
    }}
  ]
}}"""

    # ---------------------------------------------------------------------------
    # Groq request – full print() debug so output is always visible
    # ---------------------------------------------------------------------------
    try:
        api_key = _get_api_key()
        model_name = _get_model_name().strip() or 'llama-3.3-70b-versatile'

        # ── DEBUG: pre-flight checks ──────────────────────────────────────────
        print(f'[DEBUG] generate_improvement_roadmap: Groq class = {Groq}')
        print(f'[DEBUG] model = {model_name}')
        print(f'[DEBUG] api_key first 8 chars = {api_key[:8] if api_key else "MISSING"}')

        if Groq is None:
            print('[ERROR] groq package is NOT installed – run: pip install groq')
            return None
        if not api_key:
            print('[ERROR] GROQ_API_KEY is empty – check your .env file')
            return None

        # ── DEBUG: show the exact request ─────────────────────────────────────
        request_payload = {
            'model': model_name,
            'messages': [{'role': 'user', 'content': prompt[:200] + '…(truncated)'}],
        }
        print(f'[DEBUG] Request payload (prompt truncated): {request_payload}')

        # ── Make the actual API call ──────────────────────────────────────────
        client = Groq(api_key=api_key)
        chat_completion = client.chat.completions.create(
            messages=[{'role': 'user', 'content': prompt}],
            model=model_name,
            timeout=30,
        )

        # ── DEBUG: show the full raw response before any parsing ──────────────
        print(f'[DEBUG] RAW Groq response object: {chat_completion}')

        text = chat_completion.choices[0].message.content or ''
        print(f'[DEBUG] Extracted content (first 300 chars): {repr(text[:300])}')

        if not text:
            print('[WARN] generate_improvement_roadmap: Groq returned empty content')
            return None

        # Strip markdown fences if present
        cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        roadmap = json.loads(cleaned)

        # Validate required keys
        required = {'level', 'current_score', 'target_score', 'action_items'}
        if not required.issubset(roadmap.keys()):
            print(f'[WARN] generate_improvement_roadmap: missing keys – got {list(roadmap.keys())}')
            return None

        if not isinstance(roadmap['action_items'], list) or not roadmap['action_items']:
            print('[WARN] generate_improvement_roadmap: action_items is empty or not a list')
            return None

        # Enforce level consistency with our own bucketing (don't trust the model's label)
        roadmap['level'] = level
        roadmap['current_score'] = float(overall_score)
        roadmap['target_score'] = float(ROADMAP_TARGET_SCORE)

        return roadmap

    except json.JSONDecodeError as exc:
        print(f'[ERROR] generate_improvement_roadmap: JSON parse failed: {exc}')
        print(f'[ERROR] Raw text that failed to parse: {repr(text[:500]) if "text" in dir() else "(text var not set)"}')
        return None
    except Exception as exc:
        print(f'[ERROR] generate_improvement_roadmap failed: {type(exc).__name__}: {exc}')
        return None
