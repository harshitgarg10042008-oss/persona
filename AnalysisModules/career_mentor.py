"""
Feature #21 — AI Career Mentor
------------------------------
A dashboard card + conversational mentor that synthesises existing signals
(resume review, assessment scores/trends, job-match scores, readiness tier,
and optional CareerIntake) into a short narrative summary with focus areas
and next steps, plus a lightweight interactive chat.

Mirrors the established patterns from Feature #19 (AI Job Matching) and
Feature #20 (Placement Readiness Predictor):
  - deterministic data-hash keyed caching via django.core.cache
  - single _call_groq() call per generation (not on plain page load when cached)
  - graceful "not enough data" handling (no Groq call when signals are empty)
  - correct import path: from AnalysisAPI.models import ...
"""
import html
import json
import logging
import re
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from AnalysisAPI.models import ResumeReview, IndividualAssessment

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Groq helpers — reuse the exact same _call_groq from feedback_generator
# ---------------------------------------------------------------------------

try:
    from groq import Groq
except ImportError:  # pragma: no cover
    Groq = None


def _get_api_key() -> Optional[str]:
    configured_key = getattr(settings, 'GROQ_API_KEY', None)
    if configured_key:
        return configured_key
    import os
    return os.getenv('GROQ_API_KEY')


def _get_model_name() -> str:
    configured_model = getattr(settings, 'GROQ_MODEL', None)
    if configured_model:
        return configured_model
    import os
    return os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')


def _call_groq(prompt: str, timeout: int = 30, max_tokens: int = None) -> Optional[str]:
    """Send *prompt* to Groq chat completions and return the response text, or None on failure."""
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
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning('career_mentor _call_groq failed: %s', exc)
        return None


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------

def get_mentor_context(user) -> Dict[str, Any]:
    """
    Pull together all existing signals for a user:
      - Latest resume analysis (ResumeReview)
      - Assessment score trend / history (IndividualAssessment, completed)
      - Job matches (reuse #19 cached data if available — do NOT re-call Groq)
      - Readiness score + tier (reuse #20 cached data if available)
      - CareerIntake fields (target_role, timeline, concern) — all optional

    Every read handles "no data" as a normal case, never an error.
    """
    context = {
        'user_id': user.id,
        'resume': None,
        'assessments': [],
        'job_matches': None,
        'readiness': None,
        'intake': None,
        'has_sufficient_data': False,
    }

    # --- Resume ---
    latest_resume = ResumeReview.objects.filter(user=user).order_by('-created_at').first()
    if latest_resume:
        resume_info = {
            'id': latest_resume.id,
            'overall_score': latest_resume.overall_score,
            'created_at': latest_resume.created_at.isoformat() if latest_resume.created_at else None,
        }
        if latest_resume.feedback and isinstance(latest_resume.feedback, dict):
            resume_info['feedback_keys'] = list(latest_resume.feedback.keys())[:5]
            # include a compact summary of feedback
            summary_parts = []
            for key, val in latest_resume.feedback.items():
                if isinstance(val, str):
                    summary_parts.append(f"{key}: {val[:120]}")
            if summary_parts:
                resume_info['feedback_summary'] = "; ".join(summary_parts)[:600]
        context['resume'] = resume_info

    # --- Assessments ---
    recent_assessments = list(
        IndividualAssessment.objects.filter(
            user=user, status='completed', overall_score__isnull=False
        ).order_by('-completed_at')[:5]
    )
    if recent_assessments:
        for a in recent_assessments:
            entry = {
                'id': a.id,
                'role': a.platform_job_title.title if a.platform_job_title else 'Unknown',
                'overall_score': a.overall_score,
                'completed_at': a.completed_at.isoformat() if a.completed_at else None,
            }
            if a.ai_coach_strengths and isinstance(a.ai_coach_strengths, list):
                entry['strengths'] = a.ai_coach_strengths[:3]
            if a.ai_coach_weaknesses and isinstance(a.ai_coach_weaknesses, list):
                entry['weaknesses'] = a.ai_coach_weaknesses[:3]
            if a.skill_gap_analysis and isinstance(a.skill_gap_analysis, dict):
                gaps = a.skill_gap_analysis.get('skill_gaps', [])
                if gaps and isinstance(gaps, list):
                    entry['skill_gaps'] = [
                        {'skill': g.get('skill', ''), 'explanation': g.get('explanation', '')[:150]}
                        for g in gaps[:3] if isinstance(g, dict)
                    ]
            if a.communication_analysis and isinstance(a.communication_analysis, dict):
                entry['comm_summary'] = (a.communication_analysis.get('summary') or '')[:200]
            context['assessments'].append(entry)

    # --- Job Matches (reuse #19 cached data) ---
    try:
        jm_cached = cache.get(f"user_{user.id}_job_matches_v1")
        if jm_cached and isinstance(jm_cached, dict) and 'matches' in jm_cached:
            context['job_matches'] = jm_cached['matches'][:5]
    except Exception:
        pass  # never fatal

    # --- Readiness (reuse #20 cached data) ---
    try:
        pr_cached = cache.get(f"user_{user.id}_placement_readiness_v1")
        if pr_cached and isinstance(pr_cached, dict) and 'readiness' in pr_cached:
            r = pr_cached['readiness']
            context['readiness'] = {
                'total_score': r.get('total_score'),
                'tier': r.get('tier'),
            }
    except Exception:
        pass

    # --- CareerIntake (optional) ---
    try:
        from AnalysisAPI.models import CareerIntake
        intake = CareerIntake.objects.filter(user=user).order_by('-updated_at').first()
        if intake:
            context['intake'] = {
                'target_role': intake.target_role or None,
                'timeline': intake.timeline or None,
                'concern': intake.concern or None,
                'updated_at': intake.updated_at.isoformat() if intake.updated_at else None,
            }
    except Exception:
        pass

    # --- Determine if we have enough data for the Groq call ---
    has_resume = context['resume'] is not None
    has_assessments = len(context['assessments']) > 0
    context['has_sufficient_data'] = has_resume or has_assessments

    return context


# ---------------------------------------------------------------------------
# Summary generation — ONE _call_groq() call, cached
# ---------------------------------------------------------------------------

def generate_career_mentor_summary(user, refresh: bool = False) -> Dict[str, Any]:
    """
    Generate a career mentor summary for *user*.

    Returns:
        {
            'summary': str,
            'focus_areas': [str, ...],
            'next_steps': [str, ...],
            'generated_at': str  # ISO timestamp
        }

    Caching: mirrors #19/#20 — a data-hash keyed on resume id + assessment IDs.
    If a valid cached entry exists and refresh=False, return it without any Groq call.
    If the user has insufficient data, return a graceful no-data response.
    """
    context = get_mentor_context(user)

    if not context['has_sufficient_data']:
        return {
            'summary': 'Not enough data yet.',
            'focus_areas': [],
            'next_steps': [],
            'generated_at': timezone.now().isoformat(),
            'not_enough_data': True,
        }

    # Build deterministic data hash
    resume_id = context['resume']['id'] if context['resume'] else 'none'
    assessment_ids = '_'.join(str(a['id']) for a in context['assessments'])
    # Include intake updated_at in hash so intake changes invalidate the cache
    intake_ts = context.get('intake', {}).get('updated_at', '') or 'none'
    data_hash = f"res_{resume_id}_ast_{assessment_ids}_intake_{intake_ts}"
    cache_key = f"user_{user.id}_career_mentor_v1"

    if not refresh:
        cached_data = cache.get(cache_key)
        if cached_data and cached_data.get('data_hash') == data_hash:
            return cached_data['result']

    # Build the prompt context string
    context_lines = []

    if context['resume']:
        r = context['resume']
        context_lines.append(f"Resume Score: {r['overall_score']}/100")
        if r.get('feedback_summary'):
            context_lines.append(f"Resume Feedback: {r['feedback_summary']}")

    if context['assessments']:
        context_lines.append("Recent Assessment History:")
        for a in context['assessments'][:5]:
            line = f"- Role: {a['role']}, Score: {a['overall_score']}/100"
            if a.get('strengths'):
                line += f" | Strengths: {', '.join(a['strengths'][:2])}"
            if a.get('weaknesses'):
                line += f" | Weaknesses: {', '.join(a['weaknesses'][:2])}"
            if a.get('skill_gaps'):
                gaps_str = ', '.join(g.get('skill', '') for g in a['skill_gaps'] if g.get('skill'))
                if gaps_str:
                    line += f" | Skill Gaps: {gaps_str}"
            context_lines.append(line)

    if context['job_matches']:
        jm_titles = [m.get('job_title', '') for m in context['job_matches'] if m.get('job_title')]
        if jm_titles:
            context_lines.append(f"Top Matched Roles: {', '.join(jm_titles[:5])}")

    if context['readiness']:
        r = context['readiness']
        context_lines.append(f"Placement Readiness: {r.get('total_score', 'N/A')}/100 ({r.get('tier', 'N/A')})")

    if context['intake']:
        inc = context['intake']
        if inc.get('target_role'):
            context_lines.append(f"Target Role: {inc['target_role']}")
        if inc.get('timeline'):
            context_lines.append(f"Timeline: {inc['timeline']}")
        if inc.get('concern'):
            context_lines.append(f"Primary Concern: {inc['concern']}")

    candidate_context = "\n".join(context_lines)

    prompt = f"""You are an AI Career Mentor — a warm, encouraging, and honest career coach for a job-seeking candidate.

Based on the candidate's profile data below, generate a concise career mentor summary.

CANDIDATE PROFILE:
{candidate_context}

Return ONLY valid JSON (no markdown fences, no prose outside JSON) matching this exact schema:
{{
  "summary": "A warm, 2-3 sentence personalised narrative about this candidate's career trajectory and where they stand right now.",
  "focus_areas": [
    "Short label of a specific area to focus on (e.g. 'Communication Clarity')",
    "..."
  ],
  "next_steps": [
    "A specific, actionable next step (e.g. 'Complete 3 more mock interviews targeting a specific role')",
    "..."
  ]
}}

RULES:
- focus_areas: 3-5 items, each a short 2-6 word label
- next_steps: 3-5 items, each a specific actionable sentence
- Be encouraging but honest — reference actual scores and patterns from the data
- Do NOT invent metrics or skills not shown in the data above
- If intake data is provided, tailor the advice toward that target role and timeline
"""

    try:
        text = _call_groq(prompt, timeout=40)
        if not text:
            logger.warning('generate_career_mentor_summary: Groq returned empty content')
            return _fallback_summary(context)

        # Strip markdown fences
        cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        data = json.loads(cleaned)
        if not isinstance(data, dict):
            return _fallback_summary(context)

        # Validate and normalise
        summary = html.unescape(str(data.get('summary', '')).strip())
        focus_areas_raw = data.get('focus_areas', [])
        next_steps_raw = data.get('next_steps', [])

        if not summary:
            return _fallback_summary(context)

        focus_areas = [html.unescape(str(f).strip()) for f in focus_areas_raw if isinstance(f, str) and str(f).strip()][:5]
        next_steps = [html.unescape(str(n).strip()) for n in next_steps_raw if isinstance(n, str) and str(n).strip()][:5]

        result = {
            'summary': summary[:1000],
            'focus_areas': focus_areas,
            'next_steps': next_steps,
            'generated_at': timezone.now().isoformat(),
        }

        # Cache for 7 days
        cache.set(cache_key, {'data_hash': data_hash, 'result': result}, timeout=86400 * 7)
        return result

    except json.JSONDecodeError as exc:
        logger.warning('generate_career_mentor_summary: JSON parse failed: %s', exc)
        return _fallback_summary(context)
    except Exception as exc:
        logger.warning('generate_career_mentor_summary failed: %s', exc)
        return _fallback_summary(context)


def _fallback_summary(context: dict) -> dict:
    """Deterministic fallback when Groq fails — still useful, never empty."""
    lines = ['Your career profile is being analysed.']
    if context.get('assessments'):
        scores = [a['overall_score'] for a in context['assessments'] if a.get('overall_score')]
        if scores:
            avg = sum(scores) / len(scores)
            lines.append(f'Your average assessment score is {avg:.1f}/100.')
    if context.get('resume'):
        lines.append(f'Your resume scored {context["resume"]["overall_score"]}/100.')
    if context.get('readiness'):
        lines.append(f'Readiness tier: {context["readiness"].get("tier", "N/A")}.')

    return {
        'summary': ' '.join(lines),
        'focus_areas': [],
        'next_steps': [],
        'generated_at': timezone.now().isoformat(),
        'fallback': True,
    }


# ---------------------------------------------------------------------------
# Chat — separate lightweight _call_groq() call, NOT cached
# ---------------------------------------------------------------------------

MAX_HISTORY_TURNS = 10  # cap conversation history sent to Groq


def career_mentor_chat(user, message: str, conversation_history: Optional[List[Dict]] = None) -> Dict[str, Any]:
    """
    Answer a follow-up question from the user in the context of their career mentor session.

    Args:
        user: Django user
        message: The user's latest message
        conversation_history: List of prior {role, content} dicts (max 10 kept)

    Returns:
        {'reply': str}  or  {'reply': fallback_string}
    """
    if not message or not message.strip():
        return {'reply': 'Could you rephrase that?'}

    # Build context
    context = get_mentor_context(user)

    # Also pull the cached summary if it exists (so chat is aware of it)
    cached_summary = None
    try:
        cached = cache.get(f"user_{user.id}_career_mentor_v1")
        if cached and isinstance(cached, dict) and 'result' in cached:
            r = cached['result']
            if r.get('summary') and not r.get('not_enough_data'):
                cached_summary = r
    except Exception:
        pass

    # Build context text
    context_lines = []
    context_lines.append("CANDIDATE PROFILE:")
    if context.get('resume'):
        r = context['resume']
        context_lines.append(f"  Resume Score: {r['overall_score']}/100")
    if context.get('assessments'):
        for a in context['assessments'][:3]:
            line = f"  Assessment: {a['role']} ({a['overall_score']}/100)"
            if a.get('weaknesses'):
                line += f" — Weaknesses: {', '.join(a['weaknesses'][:2])}"
            context_lines.append(line)
    if context.get('readiness'):
        r = context['readiness']
        context_lines.append(f"  Readiness: {r.get('total_score', 'N/A')}/100 ({r.get('tier', 'N/A')})")
    if context.get('intake'):
        inc = context['intake']
        if inc.get('target_role'):
            context_lines.append(f"  Target Role: {inc['target_role']}")
        if inc.get('timeline'):
            context_lines.append(f"  Timeline: {inc['timeline']}")

    context_text = "\n".join(context_lines)

    # Build messages for the chat completion
    system_prompt = (
        "You are an AI Career Mentor — a warm, encouraging, and honest career coach.\n"
        "You have access to the candidate's profile data below. "
        "Answer their questions truthfully based on the data. "
        "If you don't have data for something, say so honestly rather than making things up.\n"
        "Keep answers concise (2-4 sentences unless asked for more detail)."
    )

    messages = [{"role": "system", "content": f"{system_prompt}\n\n{context_text}"}]

    # Append conversation history (last MAX_HISTORY_TURNS)
    if conversation_history:
        recent = conversation_history[-MAX_HISTORY_TURNS:]
        for turn in recent:
            role = turn.get('role', 'user')
            content = turn.get('content', '')
            if role in ('user', 'assistant') and content:
                messages.append({"role": role, "content": content})

    # Append current user message
    messages.append({"role": "user", "content": message})

    try:
        api_key = _get_api_key()
        if not api_key or Groq is None:
            return {'reply': 'AI service is temporarily unavailable. Please try again later.'}

        model_name = _get_model_name().strip() or 'llama-3.3-70b-versatile'
        client = Groq(api_key=api_key)

        chat_completion = client.chat.completions.create(
            messages=messages,
            model=model_name,
            timeout=30,
        )

        reply = chat_completion.choices[0].message.content or ''
        return {'reply': html.unescape(reply.strip())[:2000]}

    except Exception as exc:
        logger.warning('career_mentor_chat failed: %s', exc)
        return {'reply': 'I had trouble processing that. Could you try again?'}
