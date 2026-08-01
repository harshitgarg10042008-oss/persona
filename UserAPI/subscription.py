"""
Central subscription gating utility.
Provides feature-level access checks and view decorators.

OWNER bypass: SUBSCRIPTION_OWNER_EMAILS in settings — these users bypass all checks.
"""
import logging
from functools import wraps
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.contrib import messages

logger = logging.getLogger(__name__)


# ─── Owner bypass ───────────────────────────────────────────────────────────
def _get_owner_emails():
    """Return list of emails that bypass all subscription checks."""
    return getattr(settings, 'SUBSCRIPTION_OWNER_EMAILS', [])


def _is_owner(user) -> bool:
    """Check if user is the project owner (bypasses all checks)."""
    if not getattr(user, 'is_authenticated', False):
        return False
    owner_emails = _get_owner_emails()
    if not owner_emails:
        return False
    return user.email in owner_emails or user.username in owner_emails


# ─── Subscription helpers ───────────────────────────────────────────────────
def _get_subscription(user):
    """Get the SubscriptionTier for a user. Returns None if no record."""
    from UserAPI.models import SubscriptionTier
    try:
        return user.subscription
    except (SubscriptionTier.DoesNotExist, Exception):
        return None


def user_tier(user):
    """Return the tier string: 'free', 'premium', 'institution_member'."""
    if _is_owner(user):
        return 'premium'
    sub = _get_subscription(user)
    if sub is None:
        return 'free'
    return sub.tier


def user_has_premium(user) -> bool:
    """Check if user has active premium access."""
    if _is_owner(user):
        return True
    sub = _get_subscription(user)
    if sub is None:
        return False
    return sub.is_premium


def user_has_institution(user) -> bool:
    """Check if user is an active institution member."""
    if _is_owner(user):
        return True
    sub = _get_subscription(user)
    if sub is None:
        return False
    return sub.is_institution_member and sub.is_premium


def user_is_free(user) -> bool:
    """Check if user is on the free tier."""
    if _is_owner(user):
        return False
    return not user_has_premium(user)


# ─── Feature registry ───────────────────────────────────────────────────────
FEATURE_REGISTRY = {
    'resume': {'tier': 'free', 'free_limit': 3},
    'resume_analysis': {'tier': 'free', 'free_limit': 3},
    'job_matches': {'tier': 'free', 'free_limit': 3},
    'ai_interview': {'tier': 'free', 'free_interview_limit': 1},
    'voice_interviewer': {'tier': 'free', 'free_interview_limit': 1},
    'rapid_fire': {'tier': 'free', 'free_interview_limit': 1},
    'placement_readiness': {'tier': 'free'},
    'placement_readiness_score': {'tier': 'free'},
    'attire_analysis': {'tier': 'premium'},
    'body_language_analysis': {'tier': 'premium'},
    'ai_career_mentor': {'tier': 'premium'},
    'voice_personas_avatars': {'tier': 'premium'},
    'mock_placement_drive': {'tier': 'premium'},
    'panel_interview': {'tier': 'premium'},
    'ai_recruiter_dashboard': {'tier': 'premium'},
    'coding_interview_module': {'tier': 'premium'},
    'batch_cohort_dashboard': {'tier': 'premium'},
    'weak_area_analytics': {'tier': 'premium'},
    'export_pdf_csv': {'tier': 'premium'},
    'institution_export': {'tier': 'institution'},
}


def user_has_access(user, feature_name: str) -> bool:
    """
    Check if user has access to a specific feature.
    Fail-closed: returns False on any error.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if _is_owner(user):
        return True
    try:
        feature = FEATURE_REGISTRY.get(feature_name)
        if feature is None:
            logger.warning(f"Feature '{feature_name}' not in registry — defaulting to DENY")
            return False
        required_tier = feature['tier']
        if required_tier == 'free':
            return True
        if required_tier == 'premium':
            return user_has_premium(user)
        if required_tier == 'institution':
            return user_has_institution(user)
        return False
    except Exception as e:
        logger.error(f"Subscription check failed for '{feature_name}': {e}")
        return False


# ─── Usage limit helpers ────────────────────────────────────────────────────
def user_free_interview_count(user) -> int:
    """Count completed AI interviews for free-tier limit."""
    try:
        from AnalysisAPI.models import IndividualAssessment
        return IndividualAssessment.objects.filter(
            user=user, status='completed'
        ).count()
    except Exception:
        return 0


def user_free_job_match_count(user) -> int:
    """Count job match results generated."""
    try:
        from django.core.cache import cache
        # We don't have a direct count — just check if they've ever generated
        cached = cache.get(f"user_{user.id}_job_matches_v1")
        return 1 if cached else 0
    except Exception:
        return 0


def user_free_resume_review_count(user) -> int:
    """Count resume reviews uploaded."""
    try:
        from AnalysisAPI.models import ResumeReview
        return ResumeReview.objects.filter(user=user).count()
    except Exception:
        return 0


# ─── Premium-only decorator ─────────────────────────────────────────────────
def requires_premium(feature_name=''):
    """
    Decorator that blocks non-premium users from accessing a view.
    Free users get redirected to /pricing/ with a flash message.
    Owner (project admin) bypasses all checks.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not getattr(request.user, 'is_authenticated', False):
                return redirect(f"{settings.LOGIN_URL}?next={request.path}")
            if _is_owner(request.user):
                return view_func(request, *args, **kwargs)
            if not user_has_premium(request.user):
                feature = FEATURE_REGISTRY.get(feature_name, {})
                feature_desc = feature.get('description', 'this premium feature')
                if request.headers.get('Accept', '').startswith('application/json'):
                    return JsonResponse({
                        'success': False,
                        'error': 'premium_required',
                        'message': f'{feature_desc} requires a Premium subscription. Upgrade to unlock unlimited access.'
                    }, status=403)
                messages.info(request, f'Upgrade to Premium to access {feature_desc}.')
                return redirect('pricing_page')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ─── Institution-only decorator ─────────────────────────────────────────────
def requires_institution(feature_name=''):
    """
    Decorator that blocks non-institution users from accessing a view.
    Owner bypasses all checks.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not getattr(request.user, 'is_authenticated', False):
                return redirect(f"{settings.LOGIN_URL}?next={request.path}")
            if _is_owner(request.user):
                return view_func(request, *args, **kwargs)
            if not user_has_institution(request.user):
                if request.headers.get('Accept', '').startswith('application/json'):
                    return JsonResponse({
                        'success': False,
                        'error': 'institution_required',
                        'message': 'This feature requires an Institution subscription.'
                    }, status=403)
                messages.info(request, 'This feature is available only on Institution plans.')
                return redirect('pricing_page')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ─── Free-tier limit enforcement helpers ────────────────────────────────────
def check_free_interview_limit(user) -> bool:
    """Returns True if free user has NOT yet used their 1 free interview."""
    if _is_owner(user):
        return True
    if user_has_premium(user):
        return True  # unlimited
    return user_free_interview_count(user) < 1


def check_free_job_match_limit(user) -> int:
    """Returns the max number of job matches for this user (3 for free, unlimited for premium)."""
    if _is_owner(user):
        return 999
    if user_has_premium(user):
        return 999
    return 3


def get_free_user_default_persona() -> str:
    """Free users only get the default persona."""
    return 'friendly_encouraging'


def get_user_subscription_context(user):
    """
    Return a dict for template context with subscription info.
    Used to show tier badge and lock states on dashboard.
    """
    if _is_owner(user):
        return {
            'tier': 'premium',
            'tier_display': 'Premium',
            'is_premium': True,
            'is_free': False,
            'is_institution': False,
            'is_institution_member': False,
            'is_owner': True,
        }
    sub = _get_subscription(user)
    if sub is None:
        return {
            'tier': 'free',
            'tier_display': 'Free',
            'is_premium': False,
            'is_free': True,
            'is_institution': False,
            'is_institution_member': False,
            'is_owner': False,
        }
    return {
        'tier': sub.tier,
        'tier_display': sub.get_tier_display(),
        'is_premium': sub.is_premium,
        'is_free': sub.is_free,
        'is_institution': sub.is_institution_member,
        'is_institution_member': sub.is_institution_member,
        'is_owner': False,
        'premium_expires_at': sub.premium_expires_at,
        'institution_name': sub.institution.name if sub.institution else None,
    }
