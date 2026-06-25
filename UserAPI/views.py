from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .forms import IndividualSignUpForm, BusinessSignUpForm, CustomLoginForm
from .models import CustomUser, IndividualUser, BusinessUser

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
            login(request, user)
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

def login_view(request):
    if request.method == 'POST':
        form = CustomLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            
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
            
            context = {
                'user': request.user,
                'profile': individual_user,
                'total_sessions': total_sessions,
                'completed_sessions': completed_assessments.count(),
                'avg_score': avg_score,
                'recent_assessments': assessments.order_by('-created_at')[:3],
            }
            return render(request, 'dashboard/individual_dashboard.html', context)
        except AttributeError as e:
            messages.error(request, f"Error accessing individual profile: {e}")
            return redirect('home')
    else:
        # User has no profile - might be admin user or created before profile system
        messages.error(request, "No user profile found. This account may need to be set up properly.")
        return redirect('home')
