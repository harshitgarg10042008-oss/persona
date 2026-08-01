"""
Template context processor — injects subscription info into every template.
Available as `subscription` in all templates automatically.
"""
from UserAPI.subscription import get_user_subscription_context, _is_owner


def subscription_context(request):
    """
    Returns a dict with `subscription` key for template use.
    Only populated for authenticated users.
    """
    if hasattr(request, 'user') and request.user and getattr(request.user, 'is_authenticated', False):
        return {
            'subscription': get_user_subscription_context(request.user),
        }
    return {
        'subscription': None,
    }
