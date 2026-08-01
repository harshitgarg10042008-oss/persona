"""
Feature #26 — AI Recruiter Dashboard
--------------------------------------
Read-only aggregation of existing signals (resume, assessments, job matches,
readiness, solo interview feedback, panel interview verdict, placement drive
outcome) plus an AI-generated written recruiter verdict synthesising everything.

Patterns followed:
  - data-hash keyed caching via django.core.cache (same as #21)
  - single _call_groq() call per generation (not on plain page load when cached)
  - graceful "insufficient data" handling
  - correct import path: from AnalysisAPI.models import ...
  - NO new models duplicating existing data — always read from source models
"""
import hashlib
import html
import json
import logging
import re
from typing import Any, Dict, List, Optional
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Groq helpers — reuse the exact same _call_groq pattern from career_mentor
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


def _call_groq(prompt: str, timeout: int = 45, max_tokens: int = None) -> Optional[str]:
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
    except Exception as exc:
        logger.warning('recruiter_dashboard _call_groq failed: %s', exc)
        return None


# ---------------------------------------------------------------------------
# Data gathering — pulls from ALL existing source models, no duplication
# ---------------------------------------------------------------------------

# Minimum data threshold: resume + at least one of assessment/interview/drive
MIN_SECTIONS_REQUIRED = 2  # resume counts as 1, plus at least 1 other section


def _get_resume_data(user) -> Optional[Dict[str, Any]]:
    """Pull latest resume review — does NOT duplicate into a new table."""
    from AnalysisAPI.models import ResumeReview
    latest = ResumeReview.objects.filter(user=user).order_by('-created_at').first()
    if not latest:
        return None
    data = {
        'id': latest.id,
        'overall_score': latest.overall_score,
        'ats_score': latest.ats_score,
        'created_at': latest.created_at.isoformat() if latest.created_at else None,
    }
    if latest.feedback and isinstance(latest.feedback, dict):
        summary_parts = []
        for key, val in latest.feedback.items():
            if isinstance(val, str):
                summary_parts.append(f"{key}: {val[:200]}")
        if summary_parts:
            data['feedback_summary'] = "; ".join(summary_parts)[:800]
        data['feedback_keys'] = list(latest.feedback.keys())[:10]
    if latest.ats_feedback and isinstance(latest.ats_feedback, dict):
        data['ats_feedback_summary'] = str(latest.ats_feedback)[:500]
    return data


def _get_assessment_data(user) -> List[Dict[str, Any]]:
    """Pull recent completed solo assessments (not panel-drive linked ones)."""
    from AnalysisAPI.models import IndividualAssessment
    assessments = list(
        IndividualAssessment.objects.filter(
            user=user, status='completed', overall_score__isnull=False
        ).order_by('-completed_at')[:5]
    )
    result = []
    for a in assessments:
        entry = {
            'id': a.id,
            'role': a.platform_job_title.title if a.platform_job_title else 'Unknown',
            'overall_score': a.overall_score,
            'interview_mode': a.interview_mode if a.interview_mode else 'hr',
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
            entry['comm_summary'] = (a.communication_analysis.get('summary') or '')[:300]
        if a.ai_coach_summary:
            entry['coach_summary'] = str(a.ai_coach_summary)[:300]
        result.append(entry)
    return result


def _get_job_match_data(user) -> Optional[List[Dict[str, Any]]]:
    """Reuse #19 cached data — do NOT re-call Groq."""
    try:
        jm_cached = cache.get(f"user_{user.id}_job_matches_v1")
        if jm_cached and isinstance(jm_cached, dict) and 'matches' in jm_cached:
            return jm_cached['matches'][:5]
    except Exception:
        pass
    return None


def _get_readiness_data(user) -> Optional[Dict[str, Any]]:
    """Reuse #20 cached data — do NOT recompute."""
    try:
        pr_cached = cache.get(f"user_{user.id}_placement_readiness_v1")
        if pr_cached and isinstance(pr_cached, dict) and 'readiness' in pr_cached:
            r = pr_cached['readiness']
            return {
                'total_score': r.get('total_score'),
                'tier': r.get('tier'),
                'breakdown': r.get('breakdown', {}),
            }
    except Exception:
        pass
    return None


def _get_panel_interview_data(user) -> Optional[Dict[str, Any]]:
    """Pull panel interview feedback + aggregated verdict from #25."""
    from AnalysisAPI.models import IndividualAssessment, PanelSession, PanelPersonaScore
    from AnalysisModules.AnalysisAPI.voice_interviewer import PERSONAS
    # Find the most recent completed assessment with a panel session
    panel_sessions = PanelSession.objects.filter(
        assessment__user=user,
        assessment__status='completed'
    ).order_by('-created_at')
    for ps in panel_sessions:
        persona_scores = PanelPersonaScore.objects.filter(panel_session=ps)
        if not persona_scores.exists() and not ps.aggregated_score:
            continue  # skip empty panel sessions
        personas_with_scores = {}
        for ps_score in persona_scores:
            persona_info = PERSONAS.get(ps_score.persona_id, {'name': ps_score.persona_id})
            personas_with_scores[ps_score.persona_id] = {
                'name': persona_info.get('name', ps_score.persona_id),
                'score': ps_score.score,
                'feedback': ps_score.feedback[:300] if ps_score.feedback else '',
            }
        data = {
            'aggregated_score': ps.aggregated_score,
            'synthesis_summary': (ps.ai_synthesis_summary or '')[:500],
            'personas': personas_with_scores,
            'completed_at': ps.updated_at.isoformat() if ps.updated_at else None,
        }
        return data
    return None


def _get_placement_drive_data(user) -> Optional[Dict[str, Any]]:
    """Pull mock placement drive outcome from #24."""
    from AnalysisAPI.models import PlacementDrive
    drive = PlacementDrive.objects.filter(user=user).order_by('-created_at').first()
    if not drive:
        return None
    data = {
        'id': drive.id,
        'final_outcome': drive.final_outcome,
        'current_stage': drive.current_stage,
        'stage_results': drive.stage_results or {},
        'completed_at': drive.completed_at.isoformat() if drive.completed_at else None,
    }
    if drive.ai_feedback_summary:
        data['ai_feedback_summary'] = str(drive.ai_feedback_summary)[:500]
    return data


def get_recruiter_dashboard_data(user) -> Dict[str, Any]:
    """
    Pull together ALL existing signals for a user into one consolidated dict.
    This is the PART A data-gathering function. It reads from source models
    directly — no duplication, no new tables for this data.
    """
    resume = _get_resume_data(user)
    assessments = _get_assessment_data(user)
    job_matches = _get_job_match_data(user)
    readiness = _get_readiness_data(user)
    panel_interview = _get_panel_interview_data(user)
    placement_drive = _get_placement_drive_data(user)

    # Count completed sections (each non-None counts as 1)
    completed_sections = sum(1 for v in [
        resume, assessments, job_matches, readiness, panel_interview, placement_drive
    ] if v is not None)
    if resume:
        completed_sections += 0  # already counted; resume is 1 section
    # Actually recount properly:
    section_flags = [
        ('resume', resume is not None),
        ('assessments', len(assessments) > 0),
        ('job_matches', job_matches is not None),
        ('readiness', readiness is not None),
        ('panel_interview', panel_interview is not None),
        ('placement_drive', placement_drive is not None),
    ]
    completed_count = sum(1 for _, flag in section_flags if flag)

    has_sufficient_data = completed_count >= MIN_SECTIONS_REQUIRED

    return {
        'resume': resume,
        'assessments': assessments,
        'job_matches': job_matches,
        'readiness': readiness,
        'panel_interview': panel_interview,
        'placement_drive': placement_drive,
        'completed_sections': completed_count,
        'has_sufficient_data': has_sufficient_data,
        'sections_status': dict(section_flags),
    }


# ---------------------------------------------------------------------------
# AI Recruiter Verdict generation — ONE _call_groq() call, cached
# ---------------------------------------------------------------------------

def _build_data_hash(user, dashboard_data: Dict[str, Any]) -> str:
    """Build a deterministic hash from all source data to detect changes."""
    parts = []
    # Resume
    resume = dashboard_data.get('resume') or {}
    parts.append(f"resume_id_{resume.get('id', 'none')}")
    parts.append(f"resume_score_{resume.get('overall_score', 'none')}")
    # Assessments — include IDs and scores
    assessments = dashboard_data.get('assessments') or []
    ast_ids = ','.join(str(a.get('id', '')) for a in assessments[:5])
    ast_scores = ','.join(str(a.get('overall_score', '')) for a in assessments[:5])
    parts.append(f"assessments_{ast_ids}_{ast_scores}")
    # Panel interview
    panel = dashboard_data.get('panel_interview') or {}
    parts.append(f"panel_score_{panel.get('aggregated_score', 'none')}")
    parts.append(f"panel_updated_{panel.get('completed_at', 'none')}")
    # Placement drive
    drive = dashboard_data.get('placement_drive') or {}
    parts.append(f"drive_outcome_{drive.get('final_outcome', 'none')}")
    parts.append(f"drive_updated_{drive.get('completed_at', 'none')}")
    # Readiness
    readiness = dashboard_data.get('readiness') or {}
    parts.append(f"readiness_{readiness.get('total_score', 'none')}")
    raw = "|".join(parts)
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def _build_prompt_context(dashboard_data: Dict[str, Any]) -> str:
    """Build a text context string from the dashboard data for the Groq prompt."""
    lines = []

    # Resume
    resume = dashboard_data.get('resume')
    if resume:
        lines.append("RESUME:")
        lines.append(f"  Score: {resume.get('overall_score', 'N/A')}/100")
        if resume.get('ats_score') is not None:
            lines.append(f"  ATS Score: {resume['ats_score']}/100")
        if resume.get('feedback_summary'):
            lines.append(f"  Feedback: {resume['feedback_summary']}")

    # Assessments
    assessments = dashboard_data.get('assessments') or []
    if assessments:
        lines.append("SOLO INTERVIEW ASSESSMENTS:")
        for a in assessments[:5]:
            line = f"  - {a.get('role', 'Unknown')} | Score: {a.get('overall_score', 'N/A')}/100 | Mode: {a.get('interview_mode', 'hr')}"
            if a.get('strengths'):
                line += f" | Strengths: {', '.join(a['strengths'][:2])}"
            if a.get('weaknesses'):
                line += f" | Weaknesses: {', '.join(a['weaknesses'][:2])}"
            lines.append(line)

    # Job matches
    job_matches = dashboard_data.get('job_matches')
    if job_matches:
        lines.append("JOB MATCHES:")
        for m in job_matches[:5]:
            title = m.get('job_title', m.get('title', 'Unknown'))
            score = m.get('score', m.get('match_score', 'N/A'))
            lines.append(f"  - {title} (match: {score})")

    # Readiness
    readiness = dashboard_data.get('readiness')
    if readiness:
        lines.append("PLACEMENT READINESS:")
        lines.append(f"  Total: {readiness.get('total_score', 'N/A')}/100 ({readiness.get('tier', 'N/A')})")

    # Panel interview
    panel = dashboard_data.get('panel_interview')
    if panel:
        lines.append("PANEL INTERVIEW:")
        lines.append(f"  Aggregated Score: {panel.get('aggregated_score', 'N/A')}/100")
        personas = panel.get('personas') or {}
        for pid, pdata in personas.items():
            pname = pdata.get('name', pid)
            pscore = pdata.get('score', 'N/A')
            pfeedback = pdata.get('feedback', '')[:100]
            lines.append(f"  - {pname}: {pscore}/100 — {pfeedback}")
        if panel.get('synthesis_summary'):
            lines.append(f"  Synthesis: {panel['synthesis_summary']}")

    # Placement drive
    drive = dashboard_data.get('placement_drive')
    if drive:
        lines.append("MOCK PLACEMENT DRIVE:")
        lines.append(f"  Outcome: {drive.get('final_outcome', 'unknown')}")
        lines.append(f"  Stages reached: {drive.get('current_stage', 'unknown')}")
        stage_results = drive.get('stage_results') or {}
        for stage, result in stage_results.items():
            if isinstance(result, dict):
                score = result.get('score', 'N/A')
                passed = result.get('passed', 'N/A')
                lines.append(f"  - {stage}: score={score}, passed={passed}")
        if drive.get('ai_feedback_summary'):
            lines.append(f"  AI Feedback: {drive['ai_feedback_summary']}")

    return "\n".join(lines)


def generate_recruiter_verdict(user, refresh: bool = False) -> Dict[str, Any]:
    """
    Generate (or retrieve cached) AI recruiter verdict for the given user.
    Returns a dict with:
      - verdict_text: str — the AI-generated recruiter notes
      - recommendation: str — one of the clear categories
      - strengths: list[str]
      - concerns: list[str]
      - generated_at: str
      - not_enough_data: bool (True if insufficient sections completed)
      - cached: bool
    """
    from django.utils import timezone as _tz

    # Step 1: Gather all data
    dashboard_data = get_recruiter_dashboard_data(user)

    # Step 2: Check minimum data threshold
    if not dashboard_data['has_sufficient_data']:
        completed = dashboard_data['completed_sections']
        return {
            'verdict_text': (
                f"Not enough data to form a recruiter assessment. "
                f"Only {completed} of the required {MIN_SECTIONS_REQUIRED} data sections are complete. "
                f"Please complete your resume review and at least one assessment, interview, or placement drive."
            ),
            'recommendation': 'Insufficient Data',
            'strengths': [],
            'concerns': [],
            'generated_at': _tz.now().isoformat(),
            'not_enough_data': True,
            'cached': False,
        }

    # Step 3: Build data hash and check cache
    data_hash = _build_data_hash(user, dashboard_data)
    cache_key = f"user_{user.id}_recruiter_verdict_v1"

    if not refresh:
        cached_data = cache.get(cache_key)
        if cached_data and cached_data.get('data_hash') == data_hash:
            result = cached_data['result']
            result['cached'] = True
            return result

    # Step 4: Build prompt and call Groq
    context_text = _build_prompt_context(dashboard_data)
    prompt = f"""You are a senior recruiter / hiring manager reviewing a candidate's file.
You have access to the following data about this candidate from their application process.
Generate a written recruiter verdict that reads like actual recruiter notes.

CANDIDATE DATA:
{context_text}

RULES:
- Be honest and specific — reference ACTUAL scores and feedback text from the data above.
- If data for a section is missing, say so (e.g. "No panel interview data available").
- Do NOT invent scores, skills, or feedback not present in the data.
- Keep the verdict professional but direct — like internal hiring notes.
- Be constructive but candid about concerns.

Return ONLY valid JSON (no markdown fences, no prose outside JSON) matching this exact schema:
{{
  "verdict_text": "A 4-6 paragraph written summary covering overall impression, key strengths, key concerns, and final recommendation. Reference specific scores and feedback from the data.",
  "recommendation": "One of exactly: Strong Hire | Hire with Reservations | Needs Improvement | Insufficient Data",
  "strengths": [
    "Specific strength 1 (e.g. 'Strong technical knowledge demonstrated in assessment scores averaging 85/100')",
    "Specific strength 2"
  ],
  "concerns": [
    "Specific concern 1 (e.g. 'Communication score below average at 60/100 — needs improvement in articulation')",
    "Specific concern 2"
  ]
}}

If too few sections are complete to form a fair assessment, set recommendation to "Insufficient Data" and explain why.
"""

    try:
        text = _call_groq(prompt, timeout=60, max_tokens=1500)
        if not text:
            logger.warning('generate_recruiter_verdict: Groq returned empty content')
            return _fallback_verdict(dashboard_data)

        # Strip markdown fences
        cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            return _fallback_verdict(dashboard_data)

        # Validate and normalise
        verdict_text = html.unescape(str(data.get('verdict_text', '')).strip())
        recommendation = str(data.get('recommendation', 'Needs Improvement')).strip()
        valid_recs = ['Strong Hire', 'Hire with Reservations', 'Needs Improvement', 'Insufficient Data']
        if recommendation not in valid_recs:
            recommendation = 'Needs Improvement'

        strengths_raw = data.get('strengths', [])
        concerns_raw = data.get('concerns', [])

        if not verdict_text:
            return _fallback_verdict(dashboard_data)

        strengths = [html.unescape(str(s).strip()) for s in strengths_raw if isinstance(s, str) and str(s).strip()][:5]
        concerns = [html.unescape(str(c).strip()) for c in concerns_raw if isinstance(c, str) and str(c).strip()][:5]

        result = {
            'verdict_text': verdict_text[:2000],
            'recommendation': recommendation,
            'strengths': strengths,
            'concerns': concerns,
            'generated_at': _tz.now().isoformat(),
            'not_enough_data': False,
            'cached': False,
        }

        # Cache for 7 days
        cache.set(cache_key, {'data_hash': data_hash, 'result': result}, timeout=86400 * 7)
        return result

    except json.JSONDecodeError as exc:
        logger.warning('generate_recruiter_verdict: JSON parse failed: %s', exc)
        return _fallback_verdict(dashboard_data)
    except Exception as exc:
        logger.warning('generate_recruiter_verdict: unexpected error: %s', exc)
        return _fallback_verdict(dashboard_data)


def _fallback_verdict(dashboard_data: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic fallback when Groq fails — still useful, never empty."""
    from django.utils import timezone as _tz

    lines = []
    lines.append("Recruiter Assessment (auto-generated fallback):")

    resume = dashboard_data.get('resume')
    if resume:
        lines.append(f"  Resume Score: {resume.get('overall_score', 'N/A')}/100")

    assessments = dashboard_data.get('assessments') or []
    if assessments:
        scores = [a['overall_score'] for a in assessments if a.get('overall_score')]
        if scores:
            avg = sum(scores) / len(scores)
            lines.append(f"  Average Assessment Score: {avg:.1f}/100 across {len(scores)} sessions.")

    readiness = dashboard_data.get('readiness')
    if readiness:
        lines.append(f"  Readiness: {readiness.get('total_score', 'N/A')}/100 ({readiness.get('tier', 'N/A')})")

    panel = dashboard_data.get('panel_interview')
    if panel:
        lines.append(f"  Panel Score: {panel.get('aggregated_score', 'N/A')}/100")

    drive = dashboard_data.get('placement_drive')
    if drive:
        lines.append(f"  Placement Drive Outcome: {drive.get('final_outcome', 'unknown')}")

    # Determine recommendation from available data
    verdict_lines = [l.strip() for l in lines if l.strip()]
    verdict_text = "\n".join(verdict_lines)

    # Determine recommendation label
    resume_score = (resume.get('overall_score') if resume else None) or 0
    assessment_scores = [a.get('overall_score', 0) for a in assessments if a.get('overall_score')]
    avg_score = sum(assessment_scores) / len(assessment_scores) if assessment_scores else resume_score

    if avg_score >= 80:
        recommendation = 'Strong Hire'
    elif avg_score >= 60:
        recommendation = 'Hire with Reservations'
    elif avg_score >= 40:
        recommendation = 'Needs Improvement'
    else:
        recommendation = 'Insufficient Data'

    return {
        'verdict_text': verdict_text or "No data available for recruiter assessment.",
        'recommendation': recommendation,
        'strengths': [],
        'concerns': [],
        'generated_at': _tz.now().isoformat(),
        'not_enough_data': False,
        'cached': False,
        'fallback': True,
    }
