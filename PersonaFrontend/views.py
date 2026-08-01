from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

def home_view(request):
    """Landing page view"""
    return render(request, 'frontend/home.html')

@login_required
def dashboard_view(request):
    """Route users to appropriate dashboard based on type"""
    if hasattr(request.user, 'individual_profile'):
        return redirect('analysis:individual_dashboard')
    elif hasattr(request.user, 'business_profile'):
        return redirect('analysis:business_dashboard')
    else:
        # Default to individual dashboard for any user
        return redirect('analysis:individual_dashboard')

def pricing_page_view(request):
    """Pricing page — show plans and upgrade CTA."""
    context = {}
    if request.user.is_authenticated:
        from UserAPI.subscription import get_user_subscription_context, _is_owner
        context['subscription'] = get_user_subscription_context(request.user)
        context['is_owner'] = _is_owner(request.user)
    return render(request, 'frontend/pricing.html', context)
