import html
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


def _call_groq(prompt: str, timeout: int = 30, max_tokens: int = None) -> Optional[str]:
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

        kwargs = {
            "messages": [{"role": "user", "content": prompt}],
            "model": model_name,
            "timeout": timeout,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        chat_completion = client.chat.completions.create(**kwargs)
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


def get_interview_context_instruction(interview_mode: str, company_notes: str = None, is_evaluation: bool = False) -> str:
    """Shared helper for getting mode and company context instructions."""
    if not is_evaluation:
        if interview_mode == 'technical':
            mode_text = """
INTERVIEW MODE: TECHNICAL
Focus heavily on technical knowledge, skills, and role-specific expertise.
Prioritize questions about:
- Technical skills and technologies mentioned in the resume
- Problem-solving approaches and technical decisions
- System design, architecture, and implementation details
- Industry-specific technical challenges
- Tools, frameworks, and methodologies used
"""
        elif interview_mode == 'managerial':
            mode_text = """
INTERVIEW MODE: MANAGERIAL
Focus on leadership, team management, and decision-making scenarios.
Prioritize questions about:
- Team conflict resolution and people management
- Strategic thinking and ownership
- Leadership challenges and how they were handled
- Cross-functional collaboration
- Decision-making under uncertainty
"""
        elif interview_mode == 'stress':
            mode_text = """
INTERVIEW MODE: STRESS
Focus on challenging scenarios that test composure and critical thinking.
Prioritize questions about:
- Handling difficult situations or setbacks
- Dealing with ambiguity or pressure
- Responding to criticism or failure
- Making decisions with incomplete information
- Maintaining professionalism under stress
"""
        elif interview_mode == 'rapid_fire':
            mode_text = """
INTERVIEW MODE: RAPID FIRE
Focus on short, direct questions that can be answered quickly.
Prioritize questions about:
- Quick decision-making under time pressure
- Concise communication of key points
- Rapid problem identification
- High-level overview responses
- Essential knowledge recall
Keep questions brief and to the point - candidates have limited time to respond.
"""
        else:  # hr mode (default)
            mode_text = """
INTERVIEW MODE: HR
Focus on behavioral, cultural-fit, and soft skills.
Prioritize questions about:
- Teamwork and collaboration
- Leadership and communication
- Problem-solving in workplace scenarios
- Adaptability and learning
- Cultural fit and values alignment
"""
    else:
        if interview_mode == 'technical':
            mode_text = """
INTERVIEW MODE: TECHNICAL
When evaluating performance and generating follow-ups:
- Prioritize technical accuracy, depth of technical knowledge, and problem-solving approach
- Follow-ups should probe technical details, implementation decisions, or system design choices
- Consider whether the candidate demonstrates role-specific technical expertise
"""
        elif interview_mode == 'managerial':
            mode_text = """
INTERVIEW MODE: MANAGERIAL
When evaluating performance and generating follow-ups:
- Prioritize leadership qualities, decision-making rationale, and people management skills
- Follow-ups should probe for specific examples of team conflict resolution, ownership, or strategic thinking
- Consider whether the candidate demonstrates effective delegation, mentorship, and organizational impact
"""
        elif interview_mode == 'stress':
            mode_text = """
INTERVIEW MODE: STRESS
When evaluating performance and generating follow-ups:
- Prioritize composure under pressure, critical thinking in difficult situations, and professional resilience
- Follow-ups should be more challenging - probe deeper, ask "why" chains, or present hypothetical complications
- Maintain a professional but firm tone - challenge the answer without being hostile or demeaning
- Consider whether the candidate maintains clarity and professionalism when pushed
"""
        elif interview_mode == 'rapid_fire':
            mode_text = """
INTERVIEW MODE: RAPID FIRE
When evaluating performance and generating follow-ups:
- Prioritize conciseness, speed of response, and ability to hit key points quickly
- Follow-ups should be brief and direct - candidates have limited time, so don't waste it
- Consider whether the candidate communicates essential information efficiently
- Evaluate if the answer addresses the core question without unnecessary elaboration
"""
        else:  # hr mode (default)
            mode_text = """
INTERVIEW MODE: HR
When evaluating performance and generating follow-ups:
- Prioritize communication clarity, behavioral examples, and soft skills
- Follow-ups should probe for specific examples, teamwork scenarios, or cultural-fit indicators
- Consider whether the candidate demonstrates strong interpersonal and professional presence
"""
    
    if company_notes:
        if is_evaluation:
            mode_text += f"\nCOMPANY STYLE/CULTURE:\n{company_notes}\nEnsure your follow-ups and evaluation criteria heavily incorporate this company's culture and interview style."
        else:
            mode_text += f"\nCOMPANY STYLE/CULTURE:\n{company_notes}\nEnsure questions heavily incorporate this company's culture and interview style."
            
    return mode_text


def generate_question_hint(question_text: str, interview_mode: str = 'hr', company_notes: str = None) -> str:
    """Generate a single short hint for a question during Practice Mode."""
    if not question_text:
        return "Take a moment to structure your thoughts before answering."

    mode_instruction = get_interview_context_instruction(interview_mode, company_notes, is_evaluation=False)

    prompt = f"""
You are an expert interview coach assisting a candidate during a Practice Mode session.
The candidate is struggling to answer the following interview question:
"{question_text}"

{mode_instruction}

Your task: Provide ONE short, helpful hint (1-2 sentences maximum).
The hint MUST NOT give away the answer. Instead, nudge the candidate toward a good structure or approach appropriate for this specific interview mode.
For example:
- If this is a technical question, suggest thinking about edge cases, trade-offs, or time/space complexity.
- If this is a behavioral question, suggest using a specific framework (like STAR) or focusing on the impact.
- If this is a managerial question, prompt them to think about team dynamics or strategic outcomes.
Return ONLY the hint text. No quotes, no preamble.
"""
    try:
        text = _call_groq(prompt, max_tokens=100)
        if text:
            # Clean any random quotes
            return text.strip().strip('"').strip("'")
    except Exception as exc:
        logger.warning('generate_question_hint failed: %s', exc)
        
    if interview_mode == 'technical':
        return "Hint: Think about edge cases, trade-offs, or how you would optimize your solution."
    elif interview_mode == 'managerial':
        return "Hint: Focus on the strategic outcome and how you guided the team to success."
    elif interview_mode == 'stress':
        return "Hint: Take a breath. Focus on maintaining a calm, objective approach to the problem."
    elif interview_mode == 'rapid_fire':
        return "Hint: Keep it brief. State your main point directly without over-explaining."
    else:
        return "Consider structuring your answer using the STAR format: Situation, Task, Action, and Result."


def generate_tailored_questions(resume_text: str, job_role: str, num_questions: int = 5, interview_mode: str = 'hr', company_notes: str = None) -> list[str]:
    """Generate a small set of tailored interview questions from resume text."""
    if not resume_text or not job_role:
        return []

    # Mode-specific instructions
    mode_instruction = get_interview_context_instruction(interview_mode, company_notes, is_evaluation=False)

    prompt = f"""
You are an expert interview question generator.
The resume text below describes a candidate's background, experience, projects, and skills.
The target role is: {job_role}

{mode_instruction}

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
                return [html.unescape(str(q).strip()) for q in questions if str(q).strip()][:num_questions]
        except json.JSONDecodeError:
            pass

        lines = [line.strip('-* \t\n') for line in cleaned.splitlines() if line.strip()]
        questions = [html.unescape(line) for line in lines if len(line) > 10]
        return questions[:num_questions]

    except Exception as exc:
        logger.warning('Groq tailored question generation failed: %s', exc)
        return []


def generate_panel_synthesis_summary(panel_session_data: dict) -> str:
    """
    Feature #25 — Generate a synthesis summary for a panel interview.
    Combines perspectives from multiple personas and calls out significant divergences.
    """
    aggregated_score = panel_session_data.get('aggregated_score')
    persona_scores = panel_session_data.get('persona_scores', {})
    persona_roster = panel_session_data.get('persona_roster', {})
    
    # Build context for each persona's verdict
    verdicts = []
    for pid, score in persona_scores.items():
        name = persona_roster.get(pid, {}).get('name', pid)
        verdicts.append(f"- {name}: score={score}/10")
        
    prompt = f"""
You are an expert HR coordinator synthesizing feedback from a panel interview.
The panel consisted of multiple interviewers with different personas.

Aggregated Panel Score: {aggregated_score}/10

Individual Panelist Verdicts:
{chr(10).join(verdicts)}

Your task:
1. Write a single, coherent piece of feedback (2-3 paragraphs) that synthesizes the different personas' perspectives.
2. Explicitly call out if personas' assessments diverged significantly (e.g., one scored high while another scored low).
3. The tone should be professional, objective, and constructive.
4. Read as one coherent piece of feedback, not just a list of summaries.

Return ONLY the feedback text. No preamble, no quotes.
"""
    try:
        text = _call_groq(prompt)
        if text:
            return text.strip()
    except Exception as exc:
        logger.warning('generate_panel_synthesis_summary failed: %s', exc)
        
    return "A synthesis of the panel's feedback is currently unavailable."

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
            return html.unescape(text.strip())[:2000]
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

        # Unescape any HTML entities Groq may have introduced in text fields
        for item in roadmap.get('action_items', []):
            for key in ('area', 'action', 'why'):
                if isinstance(item.get(key), str):
                    item[key] = html.unescape(item[key])

        return roadmap

    except json.JSONDecodeError as exc:
        print(f'[ERROR] generate_improvement_roadmap: JSON parse failed: {exc}')
        print(f'[ERROR] Raw text that failed to parse: {repr(text[:500]) if "text" in dir() else "(text var not set)"}')
        return None
    except Exception as exc:
        print(f'[ERROR] generate_improvement_roadmap failed: {type(exc).__name__}: {exc}')
        return None


# ---------------------------------------------------------------------------
# AI Interview Coach — Comprehensive coaching system
# ---------------------------------------------------------------------------

def generate_ai_interview_coach(
    interview_transcript: str,
    questions: list,
    scores: dict,
    voice_confidence_metrics: dict = None,
    body_language_metrics: dict = None,
    resume_text: str = None,
    role: str = None
) -> Optional[dict]:
    """
    Generate comprehensive AI Interview Coach insights using Groq.

    Args:
        interview_transcript: Full transcript of the interview
        questions: List of questions asked
        scores: dict with overall_score, speaking_score, body_language_score, attire_score
        voice_confidence_metrics: Optional dict with voice confidence details
        body_language_metrics: Optional dict with body language analysis
        resume_text: Optional resume text if uploaded
        role: Job role/title for context

    Returns:
        A dict conforming to:
            {
                "summary": str,
                "strengths": [str, ...],
                "weaknesses": [str, ...],
                "action_plan": {
                    "today": [str, ...],
                    "tomorrow": [str, ...],
                    "this_week": [str, ...],
                    "next_week": [str, ...]
                },
                "recommended_topics": [str, ...]
            }
        Returns None on failure.
    """
    if not interview_transcript or not questions:
        return None

    overall_score = round(scores.get('overall_score'), 1) if scores.get('overall_score') is not None else None
    speaking_score = round(scores.get('speaking_score'), 1) if scores.get('speaking_score') is not None else None
    body_language_score = round(scores.get('body_language_score'), 1) if scores.get('body_language_score') is not None else None
    attire_score = round(scores.get('attire_score'), 1) if scores.get('attire_score') is not None else None

    # Build questions text
    questions_text = "\n".join([f"Q{i+1}: {q}" for i, q in enumerate(questions)])

    # Build voice confidence details
    voice_details = []
    if voice_confidence_metrics and isinstance(voice_confidence_metrics, dict):
        if voice_confidence_metrics.get('score'):
            voice_details.append(f"Voice confidence score: {round(voice_confidence_metrics['score'], 1)}/10")
        if voice_confidence_metrics.get('pace'):
            voice_details.append(f"Speaking pace: {voice_confidence_metrics['pace']}")
        if voice_confidence_metrics.get('clarity'):
            voice_details.append(f"Speech clarity: {voice_confidence_metrics['clarity']}")

    # Build body language details
    body_details = []
    if body_language_metrics and isinstance(body_language_metrics, dict):
        if body_language_metrics.get('posture_score'):
            body_details.append(f"Posture score: {round(body_language_metrics['posture_score'], 1)}/10")
        if body_language_metrics.get('eye_contact_score'):
            body_details.append(f"Eye contact score: {round(body_language_metrics['eye_contact_score'], 1)}/10")
        if body_language_metrics.get('gesture_score'):
            body_details.append(f"Gesture score: {round(body_language_metrics['gesture_score'], 1)}/10")

    prompt = f"""You are an expert AI interview coach providing personalized feedback to help candidates improve.

CANDIENT ROLE: {role or 'Not specified'}

INTERVIEW QUESTIONS:
{questions_text}

INTERVIEW TRANSCRIPT:
{interview_transcript}

PERFORMANCE SCORES (out of 10):
- Overall Score: {overall_score if overall_score else 'N/A'}
- Speaking & Delivery: {speaking_score if speaking_score else 'N/A'}
- Body Language: {body_language_score if body_language_score else 'N/A'}
- Professional Attire: {attire_score if attire_score else 'N/A'}

VOICE CONFIDENCE METRICS:
{chr(10).join(voice_details) if voice_details else 'No voice confidence data available'}

BODY LANGUAGE METRICS:
{chr(10).join(body_details) if body_details else 'No body language data available'}

RESUME CONTEXT:
{resume_text[:2000] if resume_text else 'No resume provided'}

TASK: Generate a comprehensive coaching report with the following sections:

1. SUMMARY: A 2-3 sentence overall summary of performance, highlighting strongest areas and areas needing improvement.

2. STRENGTHS: Generate 3-5 specific, personalized strengths based on the actual performance data. These should NOT be generic - they must reference specific observations from the transcript and scores.

3. WEAKNESSES: Generate 3-5 specific, personalized weaknesses based on the actual performance data. These should be actionable and specific to what was observed.

4. ACTION PLAN: Create a structured improvement roadmap with timeline-based actions:
   - today: 1-2 immediate actions to take today
   - tomorrow: 1-2 actions for tomorrow
   - this_week: 2-3 actions for this week
   - next_week: 2-3 actions for next week

5. RECOMMENDED TOPICS: Suggest 3-5 specific interview practice topics based on performance gaps. For example:
   - If speaking score is low → Recommend "Communication Skills" or "Public Speaking"
   - If body language is weak → Recommend "Camera Practice" or "Confidence Building"
   - If technical answers were weak → Recommend specific technical topics (SQL, System Design, etc.)
   - If behavioral questions were weak → Recommend "HR Questions" or "Behavioral Interview"

CRITICAL CONSTRAINTS:
- All content must be personalized and specific to the actual performance
- Do NOT use generic or template responses
- Base recommendations on actual score gaps and transcript analysis
- Keep all items concise and actionable
- Return ONLY valid JSON (no markdown fences, no prose outside the JSON)

Return ONLY valid JSON matching this exact schema:
{{
  "summary": "<2-3 sentence summary>",
  "strengths": ["<strength 1>", "<strength 2>", ...],
  "weaknesses": ["<weakness 1>", "<weakness 2>", ...],
  "action_plan": {{
    "today": ["<action 1>", "<action 2>"],
    "tomorrow": ["<action 1>", "<action 2>"],
    "this_week": ["<action 1>", "<action 2>", ...],
    "next_week": ["<action 1>", "<action 2>", ...]
  }},
  "recommended_topics": ["<topic 1>", "<topic 2>", ...]
}}"""

    try:
        api_key = _get_api_key()
        model_name = _get_model_name().strip() or 'llama-3.3-70b-versatile'

        if Groq is None:
            print('[ERROR] generate_ai_interview_coach: groq package is NOT installed')
            return None
        if not api_key:
            print('[ERROR] generate_ai_interview_coach: GROQ_API_KEY is empty')
            return None

        client = Groq(api_key=api_key)
        chat_completion = client.chat.completions.create(
            messages=[{'role': 'user', 'content': prompt}],
            model=model_name,
            timeout=45,  # Longer timeout for comprehensive analysis
        )

        text = chat_completion.choices[0].message.content or ''
        if not text:
            print('[WARN] generate_ai_interview_coach: Groq returned empty content')
            return None

        # Strip markdown fences if present
        cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        coaching_data = json.loads(cleaned)

        # Validate required keys
        required = {'summary', 'strengths', 'weaknesses', 'action_plan', 'recommended_topics'}
        if not required.issubset(coaching_data.keys()):
            print(f'[WARN] generate_ai_interview_coach: missing keys – got {list(coaching_data.keys())}')
            return None

        # Validate action_plan structure
        action_plan = coaching_data.get('action_plan', {})
        required_timeline = {'today', 'tomorrow', 'this_week', 'next_week'}
        if not required_timeline.issubset(action_plan.keys()):
            print(f'[WARN] generate_ai_interview_coach: action_plan missing timeline keys')
            return None

        # Ensure all fields are lists
        for field in ['strengths', 'weaknesses', 'recommended_topics']:
            if not isinstance(coaching_data.get(field), list):
                coaching_data[field] = []

        for timeline in required_timeline:
            if not isinstance(action_plan.get(timeline), list):
                action_plan[timeline] = []

        # Unescape HTML entities
        coaching_data['summary'] = html.unescape(coaching_data['summary'])
        coaching_data['strengths'] = [html.unescape(s) for s in coaching_data['strengths']]
        coaching_data['weaknesses'] = [html.unescape(w) for w in coaching_data['weaknesses']]
        coaching_data['recommended_topics'] = [html.unescape(t) for t in coaching_data['recommended_topics']]
        for timeline in required_timeline:
            action_plan[timeline] = [html.unescape(a) for a in action_plan[timeline]]

        return coaching_data

    except json.JSONDecodeError as exc:
        print(f'[ERROR] generate_ai_interview_coach: JSON parse failed: {exc}')
        print(f'[ERROR] Raw text that failed to parse: {repr(text[:500]) if "text" in dir() else "(text var not set)"}')
        return None
    except Exception as exc:
        print(f'[ERROR] generate_ai_interview_coach failed: {type(exc).__name__}: {exc}')
        return None


# ---------------------------------------------------------------------------
# Skill Gap Detection — one-shot post-completion competency analysis
# ---------------------------------------------------------------------------

def generate_skill_gap_analysis(
    *,
    job_role: str,
    response_payloads: list,
) -> Optional[dict]:
    """
    Analyze all responses for one completed assessment and return skill gaps
    vs strengths grounded in actual answer evidence.

    Args:
        job_role: Platform job title string for role context
        response_payloads: List of per-question dicts with keys:
            question_text, response_text, fluency_score, pronunciation_score,
            relevance_score, confidence_score, content_evaluation

    Returns:
        {
            "skill_gaps": [{"skill": str, "explanation": str}, ...],  # 0–6
            "strengths": [{"skill": str, "explanation": str}, ...],   # 0–4
        }
        or None on failure / insufficient evidence (caller may store null/empty).
    """
    if not response_payloads:
        return {'skill_gaps': [], 'strengths': []}

    # Require at least one non-empty answer with some signal — avoid fabricating
    usable = []
    for item in response_payloads:
        text = (item.get('response_text') or '').strip()
        eval_data = item.get('content_evaluation') or {}
        has_eval = isinstance(eval_data, dict) and (
            eval_data.get('content_correctness_score') is not None
            or (eval_data.get('explanation') or '').strip()
        )
        if text or has_eval:
            usable.append(item)

    if len(usable) < 1:
        return {'skill_gaps': [], 'strengths': []}

    lines = []
    for i, item in enumerate(usable, start=1):
        eval_data = item.get('content_evaluation') if isinstance(item.get('content_evaluation'), dict) else {}
        lines.append(
            f"--- Response {i} ---\n"
            f"Question: {item.get('question_text') or 'N/A'}\n"
            f"Answer transcript: {(item.get('response_text') or '').strip() or '(empty / skipped)'}\n"
            f"Scores: fluency={item.get('fluency_score')}, pronunciation={item.get('pronunciation_score')}, "
            f"relevance={item.get('relevance_score')}, confidence={item.get('confidence_score')}\n"
            f"Content evaluation score: {eval_data.get('content_correctness_score', 'N/A')}\n"
            f"Content evaluation notes: {(eval_data.get('explanation') or 'N/A')[:400]}"
        )

    responses_block = "\n\n".join(lines)

    prompt = f"""You are analyzing a completed practice interview for the role: {job_role or 'Not specified'}.

Below are the candidate's questions, answer transcripts, and per-question scores.
Identify skill/competency GAPS and STRENGTHS that are directly evidenced by these answers.

CANDIDATE RESPONSES:
{responses_block}

RULES:
- Return 3-6 skill_gaps ONLY if there is clear evidence of weakness in the answers. Prefer fewer over inventing filler.
- Return 2-4 strengths ONLY if there is clear evidence of strength. Prefer fewer over inventing filler.
- If evidence is thin (mostly skipped/empty/unavailable), return empty lists for both.
- Each item must name a specific skill relevant to the role (e.g. "System Design", "Behavioral Storytelling (STAR)", "SQL Query Optimization") — not vague labels like "Communication".
- Each explanation must be 1-2 sentences citing what in their answers showed the gap or strength.
- Do NOT invent generic filler. Do NOT mention scores alone without linking to answer content when a transcript exists.
- Return ONLY valid JSON (no markdown fences, no prose outside JSON).

Schema:
{{
  "skill_gaps": [
    {{"skill": "<specific skill name>", "explanation": "<1-2 sentences with evidence>"}}
  ],
  "strengths": [
    {{"skill": "<specific skill name>", "explanation": "<1-2 sentences with evidence>"}}
  ]
}}"""

    try:
        text = _call_groq(prompt, timeout=45)
        if not text:
            logger.warning('generate_skill_gap_analysis: Groq returned no response')
            return None

        cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        payload = json.loads(cleaned)

        if not isinstance(payload, dict):
            logger.warning('generate_skill_gap_analysis: response was not a JSON object')
            return None

        def _normalize_items(raw, limit):
            if not isinstance(raw, list):
                return []
            out = []
            for entry in raw[:limit]:
                if not isinstance(entry, dict):
                    continue
                skill = html.unescape(str(entry.get('skill') or '').strip())
                explanation = html.unescape(str(entry.get('explanation') or '').strip())
                if not skill or not explanation:
                    continue
                out.append({
                    'skill': skill[:120],
                    'explanation': explanation[:500],
                })
            return out

        result = {
            'skill_gaps': _normalize_items(payload.get('skill_gaps'), 6),
            'strengths': _normalize_items(payload.get('strengths'), 4),
        }
        print(
            f"[Skill Gaps] Generated {len(result['skill_gaps'])} gap(s), "
            f"{len(result['strengths'])} strength(s) for role={job_role!r}"
        )
        return result

    except json.JSONDecodeError as exc:
        logger.warning('generate_skill_gap_analysis: JSON parse failed: %s', exc)
        return None
    except Exception as exc:
        logger.warning('generate_skill_gap_analysis failed: %s', exc)
        return None


# ---------------------------------------------------------------------------
# Adaptive Interview Engine — Difficulty adjustment
# ---------------------------------------------------------------------------

def analyze_answer_and_determine_next_step(
    question_text: str,
    transcript: str,
    current_difficulty: str = 'intermediate',
    session_follow_up_count: int = 0,
    content_score: Optional[float] = None,
    voice_confidence_score: Optional[float] = None,
    body_language_score: Optional[float] = None,
    is_behavioral: bool = False,
    max_follow_ups: int = 2,
    interview_mode: str = 'hr',
    company_notes: str = None
) -> Optional[dict]:
    """
    Analyze a candidate's answer to determine the next difficulty level.

    Args:
        question_text: The question that was asked
        transcript: The candidate's transcribed answer
        current_difficulty: Current difficulty tier (beginner/intermediate/advanced)
        session_follow_up_count: How many follow-ups have been asked in this session.
        content_score: Optional content correctness score (0-10)
        voice_confidence_score: Optional voice confidence score (0-10)
        body_language_score: Optional body language score (0-10)
        interview_mode: Interview mode ('hr' or 'technical')

    Returns:
        A dict with:
            {
                "performance_score": float (0-10),
                "next_difficulty": str,
                "reason": str,
                "generate_follow_up": bool,
                "follow_up_question": Optional[str],
                "follow_up_reason": Optional[str]
            }
        Returns None on failure.
    """
    if not question_text or not transcript:
        return None

    can_generate_follow_up = session_follow_up_count < max_follow_ups

    # Build performance metrics for the prompt
    metrics = []
    if content_score is not None:
        metrics.append(f"Content correctness: {content_score:.1f}/10")
    if voice_confidence_score is not None:
        metrics.append(f"Voice confidence: {voice_confidence_score:.1f}/10")
    if body_language_score is not None:
        metrics.append(f"Body language: {body_language_score:.1f}/10")

    metrics_text = "\n".join(metrics) if metrics else "No detailed metrics available"

    # Mode-specific evaluation guidance
    mode_guidance = get_interview_context_instruction(interview_mode, company_notes, is_evaluation=True)

    # For behavioral questions, append a STAR analysis block to the same prompt.
    # This avoids a second Groq call: the model evaluates both tasks on the same read.
    _star_prompt_addendum = ''
    if is_behavioral:
        _star_prompt_addendum = """

STAR FRAMEWORK ANALYSIS (this is a behavioral question):
In addition to the adaptive difficulty fields, also evaluate whether the candidate's answer follows the STAR method (Situation, Task, Action, Result). Add these six extra keys to your JSON response:
- "star_situation": true if the candidate clearly described the Situation/context, false otherwise.
- "star_task": true if the candidate clearly described their Task or role, false otherwise.
- "star_action": true if the candidate clearly described specific Actions they personally took, false otherwise.
- "star_result": true if the candidate clearly described the Result or outcome, false otherwise.
- "star_score": a number 0-10 for overall STAR structure quality (10 = all four components present and well-developed; 0 = none present).
- "star_missing_explanation": a 1-2 sentence note on what STAR components were missing or underdeveloped. Use "All STAR components present." if all four are covered."""

    prompt = f"""You are an adaptive interview engine that adjusts question difficulty based on candidate performance.

CURRENT DIFFICULTY: {current_difficulty}

{mode_guidance}

QUESTION:
{question_text}

CANDIDATE ANSWER:
{transcript}

PERFORMANCE METRICS:
{metrics_text}

TASK: Evaluate the candidate's performance and decide the next step. You must provide two things:
1. A recommendation for the next question's difficulty.
2. A decision on whether to ask a context-aware follow-up question.

FOLLOW-UP QUESTION RULES:
- You can only generate a follow-up if the session follow-up count ({session_follow_up_count}) is less than the max ({max_follow_ups}).
- A follow-up is warranted if the answer is vague, incomplete, generic, or mentions a specific project/skill worth probing deeper.
- The follow-up question must be natural and directly related to the candidate's last answer.
- Examples: "Can you provide a specific example of that?", "What was your exact role on that project?", "Tell me more about the challenges you faced with [technology mentioned]."
- If no follow-up is needed, `generate_follow_up` must be `false`.

DIFFICULTY ADJUSTMENT RULES:
- Performance score 0-3: Poor understanding -> suggest easier questions ('beginner').
- Performance score 4-6: Adequate understanding -> maintain current difficulty ('{current_difficulty}').
- Performance score 7-10: Strong understanding -> suggest harder questions ('intermediate' or 'advanced').
- Adhere to the allowed transitions based on the current difficulty.

SCORING GUIDELINES:
- Performance score 0-3: Poor understanding, needs easier questions
- Performance score 4-6: Adequate understanding, maintain current difficulty
- Performance score 7-10: Strong understanding, increase difficulty

DIFFICULTY TRANSITIONS:
- If current is beginner: can stay beginner or move to intermediate
- If current is intermediate: can move to beginner, stay intermediate, or move to advanced
- If current is advanced: can stay intermediate or stay advanced (don't go beyond advanced)

Return ONLY valid JSON with these keys:
- `performance_score`: a number between 0 and 10 for the answer's quality.
- `next_difficulty`: one of "beginner", "intermediate", or "advanced".
- `reason`: a brief 1-2 sentence explanation for the difficulty choice.
- `generate_follow_up`: boolean `true` or `false`.
- `follow_up_question`: the text of the follow-up question if `generate_follow_up` is true, otherwise `null`.
- `follow_up_reason`: a brief explanation of why a follow-up was triggered, otherwise `null`.{_star_prompt_addendum}
"""

    try:
        # Increased timeout slightly to accommodate more complex generation
        text = _call_groq(prompt, timeout=25)
        if not text:
            logger.warning(
                'analyze_answer_and_determine_next_step: No Groq response'
            )
            return None

        # Strip markdown fences if present
        cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback for malformed JSON is less reliable but better than nothing
            perf_match = re.search(r'performance_score[^0-9]*(\d+(?:\.\d+)?)', cleaned, flags=re.IGNORECASE)
            diff_match = re.search(r'next_difficulty["\s:]+(\w+)', cleaned, flags=re.IGNORECASE)
            follow_up_match = re.search(r'generate_follow_up["\s:]+(true|false)', cleaned, flags=re.IGNORECASE)

            result = {
                'performance_score': float(perf_match.group(1)) if perf_match else 5.0,
                'next_difficulty': diff_match.group(1) if diff_match else current_difficulty,
                'reason': 'Reason not parsable from response.',
                'generate_follow_up': follow_up_match.group(1) == 'true' if follow_up_match else False,
                'follow_up_question': None, # Too complex for regex fallback
                'follow_up_reason': None,
            }
            # If regex fallback decided to generate a follow-up, we can't trust it without the text.
            if result['generate_follow_up']:
                result['generate_follow_up'] = False

        # Validate and normalize
        perf_score = result.get('performance_score', 5.0)
        try:
            perf_score = float(perf_score)
        except (TypeError, ValueError):
            perf_score = 5.0

        next_diff = result.get('next_difficulty', current_difficulty)
        valid_difficulties = {'beginner', 'intermediate', 'advanced'}
        if next_diff not in valid_difficulties:
            next_diff = current_difficulty

        # Enforce difficulty transition rules
        if current_difficulty == 'beginner' and next_diff == 'advanced':
            next_diff = 'intermediate'  # Skip directly to advanced from beginner
        elif current_difficulty == 'advanced' and next_diff == 'beginner':
            next_diff = 'intermediate'  # Drop to intermediate, not beginner

        # Handle follow-up logic
        generate_follow_up = result.get('generate_follow_up', False) and can_generate_follow_up
        follow_up_question = result.get('follow_up_question') if generate_follow_up else None
        follow_up_reason = result.get('follow_up_reason') if generate_follow_up else None

        # Final sanity check: if we decided to generate a follow-up, the text must exist.
        if generate_follow_up and not (isinstance(follow_up_question, str) and follow_up_question.strip()):
            generate_follow_up = False
            follow_up_question = None
            follow_up_reason = None

        # Extract STAR analysis for behavioral questions — best-effort, fully isolated.
        # A parse failure here yields star_analysis=None and never affects adaptive result.
        star_analysis = None
        if is_behavioral:
            try:
                raw_star_score = result.get('star_score', 0)
                star_analysis = {
                    'situation': bool(result.get('star_situation', False)),
                    'task': bool(result.get('star_task', False)),
                    'action': bool(result.get('star_action', False)),
                    'result': bool(result.get('star_result', False)),
                    'score': max(
                        0.0,
                        min(10.0, float(raw_star_score) if raw_star_score is not None else 0.0),
                    ),
                    'missing_explanation': str(result.get('star_missing_explanation', ''))[:500],
                }
            except Exception as _star_exc:
                logger.warning('STAR extraction in combined adaptive call failed: %s', _star_exc)
                star_analysis = None

        return {
            'performance_score': max(0.0, min(10.0, perf_score)),
            'next_difficulty': next_diff,
            'reason': str(result.get('reason', 'Analysis complete.'))[:500],
            'generate_follow_up': generate_follow_up,
            'follow_up_question': html.unescape(follow_up_question) if follow_up_question else None,
            'follow_up_reason': html.unescape(follow_up_reason) if follow_up_reason else None,
            'star_analysis': star_analysis,
        }

    except Exception as exc:
        logger.warning('analyze_answer_and_determine_next_step failed: %s', exc)
        return None


# ---------------------------------------------------------------------------
# STAR Framework Analysis — standalone call
# Used when adaptive engine is not invoked (adaptive mode OFF or final question)
# so there is no existing Groq call to extend for behavioral responses.
# ---------------------------------------------------------------------------

def analyze_star_framework(question_text: str, transcript: str) -> Optional[dict]:
    """
    Analyze a behavioral interview answer for STAR method structure.

    This is the standalone path invoked when ``analyze_answer_and_determine_next_step``
    is not called (adaptive mode OFF, or final question of the session).  It uses a
    single, focused ``_call_groq`` request rather than a combined prompt.

    Args:
        question_text: The behavioral question that was asked.
        transcript:    The candidate's transcribed answer.

    Returns:
        Dict with keys: situation, task, action, result (bool each),
        score (float 0-10), missing_explanation (str).
        Returns None on any Groq failure — caller stores null and logs a warning.
    """
    if not question_text or not transcript:
        return None

    prompt = f"""You are evaluating whether a behavioral interview answer follows the STAR method (Situation, Task, Action, Result).

QUESTION:
{question_text}

CANDIDATE ANSWER:
{transcript}

Evaluate the answer against the four STAR components and return ONLY valid JSON with exactly these keys:
- "situation": true if the candidate clearly described the Situation/context, false otherwise.
- "task": true if the candidate clearly described their Task or role, false otherwise.
- "action": true if the candidate clearly described specific Actions they personally took, false otherwise.
- "result": true if the candidate clearly described the Result or outcome, false otherwise.
- "star_score": a number 0-10 for overall STAR structure quality (10 = all four present and well-developed; 0 = none present).
- "missing_explanation": a 1-2 sentence note on what was missing or underdeveloped. Use "All STAR components present." if all four are covered.

Return ONLY valid JSON, no markdown fences, no prose outside the JSON."""

    try:
        text = _call_groq(prompt, timeout=20)
        if not text:
            logger.warning('analyze_star_framework: No Groq response')
            return None

        cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        result = json.loads(cleaned)

        # Accept either key name the model may use for the score
        raw_score = result.get('star_score', result.get('score', 0))
        return {
            'situation': bool(result.get('situation', False)),
            'task': bool(result.get('task', False)),
            'action': bool(result.get('action', False)),
            'result': bool(result.get('result', False)),
            'score': max(0.0, min(10.0, float(raw_score) if raw_score is not None else 0.0)),
            'missing_explanation': str(result.get('missing_explanation', ''))[:500],
        }

    except Exception as exc:
        logger.warning('analyze_star_framework failed: %s', exc)
        return None


def generate_skill_gap_analysis(job_role: str, response_payloads: list) -> Optional[dict]:
    """
    Analyze all of the candidate's responses together to identify 3-6 specific skill gaps
    and 2-4 demonstrated strengths.
    """
    if not response_payloads:
        return {'skill_gaps': [], 'strengths': []}

    # Format the responses into a clear text block
    q_and_a_text = []
    for i, payload in enumerate(response_payloads, start=1):
        q = payload.get('question_text', 'N/A')
        a = payload.get('response_text', 'N/A')
        # Skip if no real text
        if not str(a).strip():
            a = "No response provided."
        q_and_a_text.append(f"Q{i}: {q}\nA{i}: {a}\n")
        
    compiled_qa = "\n".join(q_and_a_text)
    
    prompt = f"""
You are an expert technical interviewer evaluating a candidate for a {job_role or 'General Role'} position.
Below is the transcript of their answers across the entire interview session.

Transcript:
{compiled_qa}

Based ONLY on the evidence in these answers, identify 3-6 specific skill/competency gaps and 2-4 demonstrated strengths.
If there is insufficient data (e.g. they skipped most questions or gave very short/empty answers), return empty lists rather than making up generic content. Do NOT invent generic filler content.

Return ONLY valid JSON with this exact structure:
{{
  "skill_gaps": [
    {{"skill": "Name of gap (e.g. Error Handling)", "explanation": "Brief explanation citing what they missed or got wrong in their answers."}}
  ],
  "strengths": [
    {{"skill": "Name of strength (e.g. System Design)", "explanation": "Brief explanation citing what they answered well."}}
  ]
}}
"""

    try:
        text = _call_groq(prompt, timeout=40)
        if not text:
            logger.warning('generate_skill_gap_analysis: No Groq response')
            return None

        # Strip markdown fences if present
        cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning('generate_skill_gap_analysis: Could not parse JSON from Groq')
            return None
            
        # Ensure correct structure
        skill_gaps = result.get('skill_gaps', [])
        strengths = result.get('strengths', [])
        
        # basic validation
        if not isinstance(skill_gaps, list): skill_gaps = []
        if not isinstance(strengths, list): strengths = []
        
        return {
            'skill_gaps': [gap for gap in skill_gaps if isinstance(gap, dict) and gap.get('skill') and gap.get('explanation')],
            'strengths': [strength for strength in strengths if isinstance(strength, dict) and strength.get('skill') and strength.get('explanation')]
        }

    except Exception as exc:
        logger.warning('generate_skill_gap_analysis failed: %s', exc)
        return None


def generate_learning_roadmap(job_role: str, skill_gaps: list) -> Optional[dict]:
    """
    Generate a multi-week structured learning curriculum based on identified skill gaps.
    """
    if not skill_gaps:
        return {'weeks': []}

    gaps_text = "\n".join([f"- {g.get('skill')}: {g.get('explanation')}" for g in skill_gaps])

    prompt = f"""
You are an expert technical career coach building a personalized learning roadmap for a {job_role or 'General Role'} candidate.
Below are the specific skill and competency gaps identified during their interview:

{gaps_text}

Based on these gaps, create a 3-5 week structured curriculum to help them improve.
For each week, provide a clear topic, 2-4 concrete learning objectives, and a generic suggested resource TYPE (e.g. "official documentation", "an interactive coding platform", "a system design workbook").
DO NOT fabricate specific course names, instructor names, or URLs. Keep resource types generic but descriptive.

Return ONLY valid JSON with this exact structure:
{{
  "weeks": [
    {{
      "week_title": "Week 1: [Topic]",
      "objectives": ["Objective 1", "Objective 2"],
      "resource_type": "Suggested resource type"
    }}
  ]
}}
"""

    try:
        text = _call_groq(prompt, timeout=40)
        if not text:
            logger.warning('generate_learning_roadmap: No Groq response')
            return None

        cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning('generate_learning_roadmap: Could not parse JSON from Groq')
            return None

        weeks = result.get('weeks', [])
        if not isinstance(weeks, list):
            weeks = []

        validated_weeks = []
        for w in weeks:
            if isinstance(w, dict) and w.get('week_title') and w.get('objectives') and w.get('resource_type'):
                validated_weeks.append(w)

        return {'weeks': validated_weeks}

    except Exception as exc:
        logger.warning('generate_learning_roadmap failed: %s', exc)
        return None


# ---------------------------------------------------------------------------
# AI Personality & Communication Analysis — whole-assessment, one Groq call
# ---------------------------------------------------------------------------

def generate_communication_analysis(
    *,
    job_role: str,
    response_payloads: list,
) -> Optional[dict]:
    """
    Analyze the candidate's overall communication style across a completed assessment.

    Evaluates HOW the candidate communicated (clarity, pacing, filler words, directness,
    confidence signals, structural habits) rather than WHAT they said (content correctness
    is covered by skill gaps; STAR structure is a separate feature).

    Args:
        job_role: Platform job title string for role context.
        response_payloads: List of dicts, one per response, with keys:
            question_text (str), response_text (str),
            fluency_score (float|None), pronunciation_score (float|None),
            confidence_score (float|None),
            filler_count (int|None), filler_ratio (float|None),
            words_per_minute (float|None), speaking_rate (float|None),
            pitch_variance (float|None), avg_energy (float|None).

    Returns:
        {
            "summary": "2-3 sentence overall communication summary",
            "traits": [
                {"label": "Short trait label", "explanation": "1-2 sentence evidence-based explanation"},
                ...  # 2-4 items
            ]
        }
        Returns None on any failure — caller stores null and logs a warning.
    """
    # Require at least one response with some signal
    usable = [p for p in response_payloads if (p.get('response_text') or '').strip()]
    if not usable:
        return None

    # Build a compact evidence block for each response
    evidence_lines = []
    for i, p in enumerate(usable, start=1):
        parts = [f"--- Response {i} ---"]
        parts.append(f"Question: {p.get('question_text') or 'N/A'}")
        parts.append(f"Transcript snippet: {(p.get('response_text') or '')[:400].strip() or '(empty)'}")

        metrics = []
        if p.get('fluency_score') is not None:
            metrics.append(f"fluency={p['fluency_score']:.1f}/10")
        if p.get('pronunciation_score') is not None:
            metrics.append(f"pronunciation={p['pronunciation_score']:.1f}/10")
        if p.get('confidence_score') is not None:
            metrics.append(f"confidence={p['confidence_score']:.1f}/10")
        if p.get('words_per_minute') is not None:
            metrics.append(f"pace={p['words_per_minute']:.0f} WPM")
        elif p.get('speaking_rate') is not None:
            metrics.append(f"speaking_rate={p['speaking_rate']:.2f} onsets/s")
        if p.get('filler_count') is not None:
            ratio_str = f" ({p['filler_ratio']:.1%})" if p.get('filler_ratio') is not None else ''
            metrics.append(f"filler_words={p['filler_count']}{ratio_str}")
        if p.get('avg_energy') is not None:
            metrics.append(f"vocal_energy={p['avg_energy']:.1f}/100")
        if p.get('pitch_variance') is not None:
            metrics.append(f"pitch_variance={p['pitch_variance']:.1f}/100")

        if metrics:
            parts.append("Voice metrics: " + ", ".join(metrics))
        evidence_lines.append("\n".join(parts))

    evidence_block = "\n\n".join(evidence_lines)

    prompt = f"""You are an interview communication coach analyzing a candidate's communication style.

ROLE BEING ASSESSED: {job_role or 'Not specified'}

CANDIDATE RESPONSES AND VOICE METRICS:
{evidence_block}

TASK: Based ONLY on the evidence above, identify the candidate's communication patterns — how they speak, not what they said.

STRICT RULES:
1. Focus exclusively on observable interview communication behaviours: clarity, conciseness, pacing, use of filler words, structural habits (e.g. tends to ramble vs. gets to the point), vocal confidence signals, directness.
2. Do NOT make clinical, psychological, or personality-diagnostic claims. Do NOT write "shows signs of anxiety", "introverted", "neurotic", or anything beyond interview-communication skill framing.
3. Identify 2-4 traits that are clearly evidenced by the data. Do NOT invent filler traits if evidence is thin — return fewer traits.
4. Each trait label should be short (2-6 words), e.g. "Concise and direct", "Heavy filler word usage", "Consistent vocal energy", "Tends to over-explain".
5. Each explanation must cite specific evidence (e.g. mention filler count, WPM, transcript pattern).
6. The summary must be 2-3 sentences, grounded in the data, appropriate for a candidate to read.

Return ONLY valid JSON matching this exact schema (no markdown fences, no prose outside JSON):
{{
  "summary": "<2-3 sentence overall communication summary>",
  "traits": [
    {{
      "label": "<short trait label>",
      "explanation": "<1-2 sentence evidence-based explanation>"
    }}
  ]
}}"""

    try:
        text = _call_groq(prompt, timeout=35)
        if not text:
            logger.warning('generate_communication_analysis: No Groq response')
            return None

        cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        result = json.loads(cleaned)

        if not isinstance(result, dict):
            logger.warning('generate_communication_analysis: response was not a JSON object')
            return None

        summary = str(result.get('summary') or '').strip()
        raw_traits = result.get('traits')
        if not summary or not isinstance(raw_traits, list):
            logger.warning('generate_communication_analysis: missing required keys')
            return None

        validated_traits = []
        for entry in raw_traits[:4]:  # cap at 4
            if not isinstance(entry, dict):
                continue
            label = html.unescape(str(entry.get('label') or '').strip())
            explanation = html.unescape(str(entry.get('explanation') or '').strip())
            if label and explanation:
                validated_traits.append({
                    'label': label[:100],
                    'explanation': explanation[:400],
                })

        if not validated_traits:
            logger.warning('generate_communication_analysis: no valid traits after validation')
            return None

        print(
            f"[CommAnalysis] Generated {len(validated_traits)} trait(s) for role={job_role!r}"
        )
        return {
            'summary': html.unescape(summary)[:600],
            'traits': validated_traits,
        }

    except json.JSONDecodeError as exc:
        logger.exception('generate_communication_analysis: JSON parse failed')
        return None
    except Exception as exc:
        logger.exception('generate_communication_analysis failed')
        return None

def generate_job_matches(candidate_context: str, available_jobs: list) -> Optional[list]:
    """
    Generate a ranked list of job roles that are a good match for the candidate.
    candidate_context: A summary of the candidate's resume and interview performance.
    available_jobs: A list of available job titles to choose from.
    """
    if not candidate_context or not available_jobs:
        return None

    jobs_str = "\n".join(f"- {j}" for j in available_jobs)
    
    prompt = f"""
You are an expert career advisor. Based on the candidate's profile and assessment history, recommend the top 3-5 job roles from the available list that are the best match for them.

Candidate Profile & Assessment History:
{candidate_context}

Available Job Roles:
{jobs_str}

Return ONLY valid JSON as a list of objects. Each object must have:
- job_title: The exact name of the job title from the available list
- match_score: A number from 0 to 100 representing how good of a match this is
- reason: A brief 1-2 sentence explanation of why this role matches their strengths and profile

Example format:
[
  {{
    "job_title": "Software Engineer",
    "match_score": 92,
    "reason": "The candidate has strong programming skills and their assessment highlighted excellent problem-solving abilities."
  }}
]
"""

    try:
        text = _call_groq(prompt, timeout=40)
        if not text:
            print('[WARN] generate_job_matches: Groq returned empty content')
            return None

        # Strip markdown fences if present
        cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        matches = json.loads(cleaned)

        if not isinstance(matches, list):
            print('[WARN] generate_job_matches: JSON is not a list')
            return None
        
        # Unescape and validate
        valid_matches = []
        for m in matches:
            if not isinstance(m, dict): continue
            if 'job_title' not in m or 'match_score' not in m or 'reason' not in m: continue
            
            try:
                score = int(m['match_score'])
            except ValueError:
                score = 0

            valid_matches.append({
                'job_title': html.unescape(str(m['job_title'])),
                'match_score': score,
                'reason': html.unescape(str(m['reason']))
            })
            
        # Sort by match_score descending just in case the LLM didn't
        valid_matches.sort(key=lambda x: x['match_score'], reverse=True)
        return valid_matches[:5]

    except json.JSONDecodeError as exc:
        print(f'[ERROR] generate_job_matches: JSON parse failed: {exc}')
        return None
    except Exception as exc:
        print(f'[ERROR] generate_job_matches failed: {type(exc).__name__}: {exc}')
        return None
