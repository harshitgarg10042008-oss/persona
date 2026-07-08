from django.utils import timezone
from django.db import models
from datetime import timedelta
from AnalysisAPI.models import IndividualAssessment
from UserAPI.models import IndividualUser


def get_user_achievements(user):
    """Get list of achievements unlocked by user"""
    achievements = []
    
    if not hasattr(user, 'individual_profile'):
        return achievements
    
    profile = user.individual_profile
    
    # First assessment
    completed_count = IndividualAssessment.objects.filter(
        user=user, 
        status='completed'
    ).count()
    
    if completed_count >= 1:
        achievements.append({
            'type': 'first_assessment',
            'title': 'First Steps',
            'description': 'Completed your first assessment',
            'icon': '🎯',
            'unlocked_at': IndividualAssessment.objects.filter(
                user=user, 
                status='completed'
            ).first().completed_at if completed_count > 0 else None
        })
    
    # 5 assessments
    if completed_count >= 5:
        achievements.append({
            'type': 'five_assessments',
            'title': 'Dedicated Learner',
            'description': 'Completed 5 assessments',
            'icon': '📚',
            'unlocked_at': IndividualAssessment.objects.filter(
                user=user, 
                status='completed'
            ).order_by('completed_at')[4].completed_at
        })
    
    # 7-day streak
    if profile.longest_streak >= 7:
        achievements.append({
            'type': 'week_streak',
            'title': 'Week Warrior',
            'description': 'Achieved a 7-day practice streak',
            'icon': '🔥',
            'unlocked_at': None  # Streak achievement doesn't have a specific date
        })
    
    # High scorer (average 8+)
    if completed_count >= 3:
        avg_score = IndividualAssessment.objects.filter(
            user=user,
            status='completed',
            overall_score__isnull=False
        ).aggregate(avg_score=models.Avg('overall_score'))['avg_score']
        
        if avg_score and avg_score >= 8.0:
            achievements.append({
                'type': 'high_scorer',
                'title': 'Top Performer',
                'description': 'Average score of 8+ across assessments',
                'icon': '⭐',
                'unlocked_at': None
            })
    
    return achievements


def get_latest_badge_data(user):
    """Get data for the latest unlocked achievement badge"""
    from django.db import models
    
    achievements = get_user_achievements(user)
    if not achievements:
        return None
    
    # Return the most recently unlocked achievement
    latest = max(achievements, key=lambda x: x.get('unlocked_at') or timezone.now())
    
    return {
        'user_name': user.get_full_name() or user.username,
        'achievement_title': latest['title'],
        'achievement_description': latest['description'],
        'achievement_icon': latest['icon'],
        'date': latest.get('unlocked_at') or timezone.now()
    }
