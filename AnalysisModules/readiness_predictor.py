import logging
from typing import Dict, Any, Optional
from django.utils import timezone
from AnalysisAPI.models import IndividualAssessment, ResumeReview

logger = logging.getLogger(__name__)

def calculate_placement_readiness(user) -> Dict[str, Any]:
    """
    Calculate a deterministic placement readiness score (0-100) for a candidate.
    
    Returns a dictionary with the composite score, tier, and a detailed breakdown.
    """
    now = timezone.now()
    
    # Fetch completed assessments (up to 5 most recent)
    assessments_qs = IndividualAssessment.objects.filter(
        user=user, 
        status='completed', 
        overall_score__isnull=False
    ).order_by('-completed_at')[:5]
    
    # Reverse to chronological order (oldest to newest among the latest 5)
    recent_assessments = list(reversed(list(assessments_qs)))
    num_assessments = len(recent_assessments)
    
    score_breakdown = {
        'performance_base': {'score': 0, 'max': 25, 'description': ''},
        'performance_trend': {'score': 0, 'max': 20, 'description': ''},
        'resume_quality': {'score': 0, 'max': 25, 'description': ''},
        'practice_volume': {'score': 0, 'max': 10, 'description': ''},
        'practice_recency': {'score': 0, 'max': 10, 'description': ''},
        'coach_gaps': {'score': 0, 'max': 10, 'description': ''},
    }
    
    # --- Component 1: Assessment Performance (Base + Trend) ---
    if num_assessments > 0:
        # Base: Average of the recent assessments (up to last 3)
        last_3 = recent_assessments[-3:]
        avg_score = sum(a.overall_score for a in last_3) / len(last_3)
        base_points = (avg_score / 100.0) * 25
        score_breakdown['performance_base']['score'] = round(base_points, 1)
        score_breakdown['performance_base']['description'] = f"Average score of {avg_score:.1f}% across recent assessments."
        
        # Trend
        if len(last_3) >= 2:
            oldest = last_3[0].overall_score
            latest = last_3[-1].overall_score
            diff = latest - oldest
            if diff > 5:
                trend_pts = 20
                desc = "Consistent improvement across recent assessments."
            elif diff >= -5:
                trend_pts = 10
                desc = "Performance is stable."
            else:
                trend_pts = 5
                desc = "Scores have declined recently."
        else:
            # Only 1 assessment
            trend_pts = 10
            desc = "Neutral trend (only one assessment completed)."
            
        score_breakdown['performance_trend']['score'] = trend_pts
        score_breakdown['performance_trend']['description'] = desc
    else:
        score_breakdown['performance_base']['description'] = "No completed assessments."
        score_breakdown['performance_trend']['description'] = "No completed assessments."
        
    # --- Component 2: Resume Quality ---
    latest_resume = ResumeReview.objects.filter(user=user).order_by('-created_at').first()
    if latest_resume and latest_resume.overall_score:
        resume_pts = (latest_resume.overall_score / 100.0) * 25
        score_breakdown['resume_quality']['score'] = round(resume_pts, 1)
        score_breakdown['resume_quality']['description'] = f"Resume score of {latest_resume.overall_score:.1f}%."
    else:
        score_breakdown['resume_quality']['score'] = 0
        score_breakdown['resume_quality']['description'] = "No resume uploaded. Upload a resume to boost your readiness."
        
    # --- Component 3: Practice Volume & Recency ---
    # Volume
    total_completed = IndividualAssessment.objects.filter(user=user, status='completed').count()
    if total_completed >= 3:
        vol_pts = 10
        vol_desc = "Strong practice history (3+ assessments)."
    elif total_completed > 0:
        vol_pts = 5
        vol_desc = "Minimal practice history (less than 3 assessments)."
    else:
        vol_pts = 0
        vol_desc = "No practice history."
        
    score_breakdown['practice_volume']['score'] = vol_pts
    score_breakdown['practice_volume']['description'] = vol_desc
    
    # Recency
    if num_assessments > 0:
        latest_assessment = recent_assessments[-1]
        if latest_assessment.completed_at:
            days_ago = (now - latest_assessment.completed_at).days
            if days_ago <= 14:
                rec_pts = 10
                rec_desc = "Recent practice within the last 2 weeks."
            else:
                rec_pts = 0
                rec_desc = f"Last practice was {days_ago} days ago. Keep practicing!"
        else:
            rec_pts = 0
            rec_desc = "Could not determine recency."
    else:
        rec_pts = 0
        rec_desc = "No practice history."
        
    score_breakdown['practice_recency']['score'] = rec_pts
    score_breakdown['practice_recency']['description'] = rec_desc

    # --- Component 4: AI Coach Gaps ---
    if num_assessments > 0:
        latest_assessment = recent_assessments[-1]
        weaknesses = latest_assessment.ai_coach_weaknesses or []
        num_weaknesses = len(weaknesses)
        if num_weaknesses <= 1:
            gap_pts = 10
            gap_desc = "Few to zero significant weaknesses detected."
        elif num_weaknesses <= 3:
            gap_pts = 5
            gap_desc = "A few weaknesses to work on."
        else:
            gap_pts = 0
            gap_desc = "Multiple significant weaknesses detected."
    else:
        gap_pts = 0
        gap_desc = "No assessments to analyze for weaknesses."
        
    score_breakdown['coach_gaps']['score'] = gap_pts
    score_breakdown['coach_gaps']['description'] = gap_desc
    
    # --- Total Score Calculation ---
    total_score = sum(item['score'] for item in score_breakdown.values())
    total_score = round(total_score, 1)
    
    # --- Determine Tier ---
    if num_assessments == 0:
        tier = "Not Enough Data"
        total_score = 0
    elif total_score >= 80:
        tier = "Interview Ready"
    elif total_score >= 60:
        tier = "Getting There"
    else:
        tier = "Needs Practice"
        
    return {
        'total_score': total_score,
        'tier': tier,
        'breakdown': score_breakdown,
        'has_data': num_assessments > 0
    }
