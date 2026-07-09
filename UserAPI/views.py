from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib import messages
from django.http import JsonResponse
import json
from django.conf import settings
from django_ratelimit.decorators import ratelimit
from .forms import IndividualSignUpForm, BusinessSignUpForm, CustomLoginForm
from .models import CustomUser, IndividualUser, BusinessUser, InstitutionMembership


def _apply_session_preference(request, remember_me):
    if remember_me:
        request.session.set_expiry(60 * 60 * 24 * 30)
    else:
        request.session.set_expiry(0)


@ratelimit(key='ip', rate=settings.RATE_LIMIT_AUTH, block=True, method='POST')
def signup_view(request):
    if request.method == 'POST':
        user_type = request.POST.get('user_type')
        
        if user_type == 'individual':
            form = IndividualSignUpForm(request.POST)
        elif user_type == 'business':
            form = BusinessSignUpForm(request.POST)
        else:
            messages.error(request, 'Invalid user type.')
            return redirect('signup')
        
        if form.is_valid():
            user = form.save()
            remember_me = request.POST.get('remember_me') == 'on'
            login(request, user)
            _apply_session_preference(request, remember_me)
            messages.success(request, f'Welcome to Persona! Your {user_type} account has been created successfully.')
            
            # Redirect based on user type
            if user_type == 'business':
                return redirect('analysis:business_dashboard')
            else:
                return redirect('individual_dashboard')
        else:
            # Pass form errors to template
            context = {
                'individual_form': IndividualSignUpForm(),
                'business_form': BusinessSignUpForm(),
                'active_tab': user_type,
                'form_errors': form.errors
            }
            return render(request, 'auth/signup.html', context)
    
    context = {
        'individual_form': IndividualSignUpForm(),
        'business_form': BusinessSignUpForm(),
        'active_tab': 'individual'
    }
    return render(request, 'auth/signup.html', context)

@ratelimit(key='ip', rate=settings.RATE_LIMIT_AUTH, block=True, method='POST')
def login_view(request):
    if request.method == 'POST':
        form = CustomLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            remember_me = request.POST.get('remember_me') == 'on'
            login(request, user)
            _apply_session_preference(request, remember_me)
            
            # Determine user type for personalized message and redirect
            if hasattr(user, 'business_profile'):
                messages.success(request, f'Welcome back!')
                return redirect('analysis:business_dashboard')
            else:
                messages.success(request, f'Welcome back!')
                return redirect('individual_dashboard')
        else:
            context = {
                'login_form': form,
                'form_errors': form.errors
            }
            return render(request, 'auth/login.html', context)
    
    context = {
        'login_form': CustomLoginForm()
    }
    return render(request, 'auth/login.html', context)

def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('home')

def dashboard_view(request):
    """Legacy dashboard - redirect to appropriate dashboard based on user type"""
    if not request.user.is_authenticated:
        return redirect('login')
    
    # Redirect to appropriate dashboard
    if hasattr(request.user, 'business_profile'):
        return redirect('analysis:business_dashboard')
    else:
        return redirect('individual_dashboard')

def individual_dashboard_view(request):
    """Dashboard for individual users"""
    if not request.user.is_authenticated:
        return redirect('login')
    
    # Check if user has business profile first
    if hasattr(request.user, 'business_profile'):
        messages.error(request, "Access denied. Business users should use the business dashboard.")
        return redirect('analysis:business_dashboard')
    
    # Check if user has individual profile
    if hasattr(request.user, 'individual_profile'):
        try:
            individual_user = request.user.individual_profile
            
            # Get assessment statistics
            from AnalysisAPI.models import IndividualAssessment, PlatformJobTitle
            
            assessments = IndividualAssessment.objects.filter(
                user=request.user  # Use request.user instead of individual_user
            )
            
            completed_assessments = assessments.filter(status='completed')
            total_sessions = assessments.count()
            avg_score = None
            
            if completed_assessments.exists():
                scores = [a.overall_score for a in completed_assessments if a.overall_score]
                if scores:
                    avg_score = sum(scores) / len(scores)
            
            # Get institution memberships
            institution_memberships = individual_user.institution_memberships.filter(is_active=True)
            
            context = {
                'user': request.user,
                'profile': individual_user,
                'total_sessions': total_sessions,
                'completed_sessions': completed_assessments.count(),
                'avg_score': avg_score,
                'recent_assessments': assessments.order_by('-created_at')[:3],
                'current_streak': individual_user.current_streak,
                'longest_streak': individual_user.longest_streak,
                'institution_memberships': institution_memberships,
            }
            return render(request, 'dashboard/individual_dashboard.html', context)
        except AttributeError as e:
            messages.error(request, f"Error accessing individual profile: {e}")
            return redirect('home')
    else:
        # User has no profile - might be admin user or created before profile system
        messages.error(request, "No user profile found. This account may need to be set up properly.")
        return redirect('home')

@login_required
def join_institution(request):
    """Join an institution using an institution code"""
    if request.method == 'POST':
        institution_code = request.POST.get('institution_code', '').strip()
        
        if not institution_code:
            messages.error(request, 'Please enter an institution code.')
            return redirect('individual_dashboard')
        
        # Check if user has business profile
        if hasattr(request.user, 'business_profile'):
            messages.error(request, 'Business users cannot join institutions.')
            return redirect('analysis:business_dashboard')
        
        # Check if user has individual profile
        if not hasattr(request.user, 'individual_profile'):
            messages.error(request, 'Individual profile required to join institutions.')
            return redirect('individual_dashboard')
        
        # Parse institution code
        try:
            business_id = int(institution_code.replace('INST-', ''))
            business = BusinessUser.objects.get(id=business_id)
        except (ValueError, BusinessUser.DoesNotExist):
            messages.error(request, 'Invalid institution code.')
            return redirect('individual_dashboard')
        
        # Check if already a member
        existing_membership = InstitutionMembership.objects.filter(
            individual=request.user.individual_profile,
            business=business
        ).first()
        
        if existing_membership:
            if existing_membership.is_active:
                messages.info(request, f'You are already a member of {business.company_name or business.name}.')
            else:
                existing_membership.is_active = True
                existing_membership.save()
                messages.success(request, f'Your membership to {business.company_name or business.name} has been reactivated.')
            return redirect('individual_dashboard')
        
        # Check consent
        consent_granted = request.POST.get('consent_granted') == 'on'
        if not consent_granted:
            messages.error(request, 'You must consent to share your assessment results with the institution.')
            return redirect('individual_dashboard')
        
        # Create membership
        from django.utils import timezone
        membership = InstitutionMembership.objects.create(
            individual=request.user.individual_profile,
            business=business,
            consent_granted=True,
            consent_granted_at=timezone.now()
        )
        
        messages.success(request, f'Successfully joined {business.company_name or business.name}!')
        return redirect('individual_dashboard')
    
    return redirect('individual_dashboard')
