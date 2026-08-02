"""
Central subscription gating utility.
Provides feature-level access checks and view decorators.

OWNER bypass: SUBSCRIPTION_OWNER_EMAILS in settings — these users bypass all checks.

FREE TIER LIMITS (per calendar month, computed live — no stored counters):
  - 1 AI Interview per calendar month (resets on 1st of each month)
  - Top 3 AI Job Matches only
  - Speech module only (Attire + Body Language blocked)
  - Placement Readiness Score (numeric only, no detailed breakdown)

PREMIUM TIER:
  - Unlimited AI Interviews & retakes
  - Unlimited AI Job Matches
  - Full Resume Analysis (Attire + Body Language + Speech)
  - AI Career Mentor, Voice Personas/Avatars, Mock Placement Drive
  - Panel Interview, AI Recruiter Dashboard

INSTITUTION TIER:
  - Everything in Premium for all linked students
  - Batch/Cohort Dashboard, Weak-area analytics, PDF/CSV export
"""
import logging
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.contrib import messages
from django.utils import timezone

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
    # Free-tier features (with limits enforced separately)
    'resume':              {'tier': 'free'},
    'resume_analysis':     {'tier': 'free'},
    'job_matches':         {'tier': 'free'},
    'ai_interview':        {'tier': 'free', 'free_interview_limit': 2},
    'voice_interviewer':   {'tier': 'free', 'free_interview_limit': 2},
    'rapid_fire':          {'tier': 'premium'},
    'placement_readiness':         {'tier': 'free'},
    'placement_readiness_score':   {'tier': 'free'},
    'placement_readiness_detail':  {'tier': 'premium'},  # detailed breakdown
    # Premium-only features
    'attire_analysis':             {'tier': 'premium'},
    'body_language_analysis':      {'tier': 'premium'},
    'ai_career_mentor':            {'tier': 'premium'},
    'voice_personas_avatars':      {'tier': 'premium'},
    'mock_placement_drive':        {'tier': 'premium'},
    'panel_interview':             {'tier': 'premium'},
    'ai_recruiter_dashboard':      {'tier': 'premium'},
    'coding_interview_module':     {'tier': 'premium'},  # #27 — gated when built
    # Institution-only features
    'batch_cohort_dashboard': {'tier': 'institution'},
    'weak_area_analytics':    {'tier': 'institution'},
    'export_pdf_csv':         {'tier': 'institution'},
    'institution_export':     {'tier': 'institution'},
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
def _current_month_start():
    """
    Return a timezone-aware datetime for the first moment of the current
    calendar month, using Django's configured TIME_ZONE.
    """
    now = timezone.localtime(timezone.now())
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month_start():
    """Return the first moment of the next calendar month (timezone-aware)."""
    now = _current_month_start()
    # Add ~32 days then normalize to first of month
    next_month = now + timedelta(days=32)
    return next_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _format_next_reset_date():
    """Return a human-readable string for when the free interview resets."""
    next_month = _next_month_start()
    return next_month.strftime('%B %d, %Y')


def user_free_interview_count(user) -> int:
    """
    Count completed AI interviews for the CURRENT CALENDAR MONTH only.
    This computes live — no stored counter needed. Resets automatically
    every month since it queries created_at >= start_of_current_month.
    """
    try:
        from AnalysisAPI.models import IndividualAssessment
        month_start = _current_month_start()
        return IndividualAssessment.objects.filter(
            user=user,
            status='completed',
            created_at__gte=month_start,
        ).count()
    except Exception:
        return 0


def check_free_interview_limit(user) -> bool:
    """
    Returns True if free user has NOT yet used their 2 free interviews
    for the current calendar month.
    Premium/owner users always return True (unlimited).
    """
    if _is_owner(user):
        return True
    if user_has_premium(user):
        return True  # unlimited
    return user_free_interview_count(user) < 2


def check_free_interview_remaining(user) -> dict:
    """
    Return detailed info about free interview usage.
    Used for UI messages.
    """
    if _is_owner(user):
        return {'allowed': True, 'count': 0, 'limit': 999, 'reset_date': None, 'is_owner': True}
    if user_has_premium(user):
        return {'allowed': True, 'count': 0, 'limit': 999, 'reset_date': None, 'is_owner': False}
    count = user_free_interview_count(user)
    remaining = max(0, 2 - count)
    return {
        'allowed': remaining > 0,
        'count': count,
        'limit': 2,
        'remaining': remaining,
        'reset_date': _format_next_reset_date(),
        'is_owner': False,
    }


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
            'interview_reset_date': None,
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
            'interview_reset_date': _format_next_reset_date(),
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
        'interview_reset_date': _format_next_reset_date() if sub.is_free else None,
    }


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


# ─── Free-tier interview limit decorator ────────────────────────────────────
def requires_interview_slot(feature_name='ai_interview'):
    """
    Decorator that enforces the free-tier monthly interview limit.
    Free users can only start 2 interviews per calendar month.
    Premium users have unlimited interviews.
    Owner bypasses all checks.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not getattr(request.user, 'is_authenticated', False):
                return redirect(f"{settings.LOGIN_URL}?next={request.path}")
            if _is_owner(request.user):
                return view_func(request, *args, **kwargs)
            if user_has_premium(request.user):
                return view_func(request, *args, **kwargs)
            # Free user — check monthly limit
            if not check_free_interview_limit(request.user):
                reset_date = _format_next_reset_date()
                if request.headers.get('Accept', '').startswith('application/json'):
                    return JsonResponse({
                        'success': False,
                        'error': 'interview_limit_reached',
                        'message': f"You've used your 2 free interviews for this month. "
                                   f"Your next free interview unlocks on {reset_date}. "
                                   f"Upgrade to Premium for unlimited interviews.",
                        'reset_date': reset_date,
                    }, status=429)
                messages.error(
                    request,
                    f"You've used your 2 free interviews for this month. "
                    f"Your next free interview unlocks on {reset_date}. "
                    f"Upgrade to Premium for unlimited interviews."
                )
                return redirect('pricing_page')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ─── Admin: Activate/Deactivate premium for users ───────────────────────────
def activate_premium_for_user(user, duration_days=None, institution=None):
    """
    Activate Premium for a specific user.
    - duration_days=None means lifetime premium (no expiry)
    - duration_days=30 means 30-day premium
    - institution=None means individual premium (not institution member)

    Returns: (success: bool, message: str)
    """
    from UserAPI.models import SubscriptionTier

    try:
        sub, created = SubscriptionTier.objects.get_or_create(user=user)

        if created:
            sub.tier = 'premium'
            sub.is_active = True
            if duration_days:
                sub.premium_expires_at = timezone.now() + timedelta(days=duration_days)
            else:
                sub.premium_expires_at = None  # lifetime
            sub.institution = institution
            sub.save()
            expiry_str = sub.premium_expires_at.strftime('%B %d, %Y') if sub.premium_expires_at else 'lifetime'
            return True, f"Activated {duration_days or 'lifetime'} premium for {user.email} (expires: {expiry_str})."
        else:
            sub.tier = 'premium'
            sub.is_active = True
            if duration_days:
                sub.premium_expires_at = timezone.now() + timedelta(days=duration_days)
            else:
                sub.premium_expires_at = None  # lifetime
            sub.institution = institution
            sub.save()
            expiry_str = sub.premium_expires_at.strftime('%B %d, %Y') if sub.premium_expires_at else 'lifetime'
            return True, f"Updated {user.email} to premium (expires: {expiry_str})."
    except Exception as e:
        logger.error(f"Failed to activate premium for {user.email}: {e}")
        return False, f"Error activating premium for {user.email}: {str(e)}"


def deactivate_premium_for_user(user):
    """
    Deactivate premium for a user, reverting them to free tier.
    Owner email cannot be deactivated this way.
    """
    from UserAPI.models import SubscriptionTier

    if _is_owner(user):
        return False, "Cannot deactivate owner account."

    try:
        sub = SubscriptionTier.objects.get(user=user)
        sub.tier = 'free'
        sub.is_active = True  # still active as a free tier
        sub.premium_expires_at = None
        sub.institution = None
        sub.save()
        return True, f"Deactivated premium for {user.email}."
    except SubscriptionTier.DoesNotExist:
        return True, f"{user.email} already has no premium tier."
    except Exception as e:
        logger.error(f"Failed to deactivate premium for {user.email}: {e}")
        return False, f"Error deactivating premium for {user.email}: {str(e)}"


def list_free_users():
    """
    Return all users who are on the free tier.
    Used by admin to see who can be upgraded.
    """
    from django.contrib.auth import get_user_model
    from UserAPI.models import SubscriptionTier
    User = get_user_model()

    owner_emails = _get_owner_emails()
    users = []
    for user in User.objects.filter(is_active=True).exclude(email__in=owner_emails):
        try:
            sub = user.subscription
            if sub.tier == 'free':
                users.append({
                    'email': user.email,
                    'username': user.username,
                    'date_joined': user.date_joined,
                    'tier': 'free',
                })
        except Exception:
            # No subscription record = free
            users.append({
                'email': user.email,
                'username': user.username,
                'date_joined': user.date_joined,
                'tier': 'free',
            })
    return users
