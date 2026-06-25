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
