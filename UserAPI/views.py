from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
import json
import logging
from django.conf import settings
from django_ratelimit.decorators import ratelimit
from django.core.mail import send_mail
from .forms import IndividualSignUpForm, BusinessSignUpForm, CustomLoginForm
from .models import CustomUser, IndividualUser, BusinessUser, InstitutionMembership, SalesInquiry
from .subscription import requires_premium

logger = logging.getLogger(__name__)


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

            if user_type == 'business':
                return redirect('analysis:business_dashboard')
            else:
                return redirect('individual_dashboard')
        else:
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

    if hasattr(request.user, 'business_profile'):
        return redirect('analysis:business_dashboard')
    else:
        return redirect('individual_dashboard')


def individual_dashboard_view(request):
    """Dashboard for individual users"""
    if not request.user.is_authenticated:
        return redirect('login')

    if hasattr(request.user, 'business_profile'):
        messages.error(request, "Access denied. Business users should use the business dashboard.")
        return redirect('analysis:business_dashboard')

    if hasattr(request.user, 'individual_profile'):
        try:
            individual_user = request.user.individual_profile

            from AnalysisAPI.models import IndividualAssessment, PlatformJobTitle

            assessments = IndividualAssessment.objects.filter(user=request.user)
            completed_assessments = assessments.filter(status='completed')
            total_sessions = assessments.count()
            avg_score = None

            if completed_assessments.exists():
                scores = [a.overall_score for a in completed_assessments if a.overall_score is not None]
                if scores:
                    avg_score = sum(scores) / len(scores)

            institution_memberships = individual_user.institution_memberships.filter(is_active=True)

            import json as _json
            scored_assessments = completed_assessments.filter(
                overall_score__isnull=False
            ).order_by('completed_at')
            chart_dates = []
            chart_scores = []
            for a in scored_assessments:
                if a.completed_at:
                    chart_dates.append(a.completed_at.strftime('%b %d'))
                    chart_scores.append(float(a.overall_score))
            chart_data = {'labels': chart_dates, 'scores': chart_scores}

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
                'chart_json': _json.dumps(chart_data),
            }
            return render(request, 'dashboard/individual_dashboard.html', context)
        except AttributeError as e:
            messages.error(request, f"Error accessing individual profile: {e}")
            return redirect('home')
    else:
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

        if hasattr(request.user, 'business_profile'):
            messages.error(request, 'Business users cannot join institutions.')
            return redirect('analysis:business_dashboard')

        if not hasattr(request.user, 'individual_profile'):
            messages.error(request, 'Individual profile required to join institutions.')
            return redirect('individual_dashboard')

        try:
            business_id = int(institution_code.replace('INST-', ''))
            business = BusinessUser.objects.get(id=business_id)
        except (ValueError, BusinessUser.DoesNotExist):
            messages.error(request, 'Invalid institution code.')
            return redirect('individual_dashboard')

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

        consent_granted = request.POST.get('consent_granted') == 'on'
        if not consent_granted:
            messages.error(request, 'You must consent to share your assessment results with the institution.')
            return redirect('individual_dashboard')

        from django.utils import timezone
        InstitutionMembership.objects.create(
            individual=request.user.individual_profile,
            business=business,
            consent_granted=True,
            consent_granted_at=timezone.now()
        )

        messages.success(request, f'Successfully joined {business.company_name or business.name}!')
        return redirect('individual_dashboard')

    return redirect('individual_dashboard')


@login_required
def user_settings_view(request):
    """User settings page for managing account preferences"""
    if not hasattr(request.user, 'individual_profile'):
        messages.error(request, 'Individual profile required to access settings.')
        return redirect('home')

    profile = request.user.individual_profile

    if request.method == 'POST':
        media_retention_days = request.POST.get('media_retention_days')

        if media_retention_days in ['15', '30', '60']:
            profile.media_retention_days = int(media_retention_days)
            profile.save()
            messages.success(request, 'Settings saved successfully.')
        else:
            messages.error(request, 'Invalid media retention setting.')

        return redirect('user_settings')

    context = {
        'user': request.user,
        'profile': profile,
    }
    return render(request, 'user/settings.html', context)


# ─── Feature #22 — Voice Interviewer Personas ─────────────────────────────────

from AnalysisAPI.voice_interviewer import PERSONAS
from .models import UserInterviewerPreference


@login_required
@requires_premium('voice_personas_avatars')
def get_personas_view(request):
    """Return available personas and the user's current preference."""
    try:
        pref = request.user.interviewer_preference
        current = pref.persona_id
    except UserInterviewerPreference.DoesNotExist:
        current = 'friendly_encouraging'

    return JsonResponse({
        'personas': list(PERSONAS.values()),
        'current_preference': current
    })


@login_required
@requires_premium('voice_personas_avatars')
def update_persona_preference(request):
    """Save the user's chosen interviewer persona."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            persona_id = data.get('persona_id')

            if persona_id not in PERSONAS:
                return JsonResponse({'error': 'Invalid persona'}, status=400)

            pref, created = UserInterviewerPreference.objects.get_or_create(
                user=request.user,
                defaults={'persona_id': persona_id}
            )

            if not created:
                pref.persona_id = persona_id
                pref.save()

            return JsonResponse({'status': 'success', 'message': 'Preference saved successfully'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required
def pricing_page_view(request):
    """Render the pricing page with user context."""
    from django.conf import settings
    # Get user's current subscription status
    try:
        sub = request.user.subscription
        is_premium = sub.is_premium
        tier = sub.tier
        expires_at = sub.premium_expires_at
    except Exception:
        is_premium = False
        tier = 'free'
        expires_at = None

    context = {
        'plans': settings.PLAN_PRICING,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        'is_premium': is_premium,
        'tier': tier,
        'expires_at': expires_at.strftime('%B %d, %Y') if expires_at else None,
    }
    return render(request, 'pricing.html', context)


def debug_urls(request):
    from django.urls import get_resolver
    from django.http import HttpResponse
    resolver = get_resolver()
    keys = [k for k in resolver.reverse_dict.keys() if isinstance(k, str)]
    return HttpResponse("<br>".join(keys))


@csrf_exempt
@ratelimit(key='ip', rate='5/h', block=True, method='POST')
def sales_inquiry(request):
    """Handle B2B sales inquiry submissions for Institution/Enterprise plans."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST requests allowed'}, status=405)

    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        institution_name = data.get('institution_name', '').strip()
        phone = data.get('phone', '').strip() or None
        plan_interest = data.get('plan_interest', '').strip()
        message = data.get('message', '').strip() or None

        # Validate required fields
        if not name or not email or not institution_name or not plan_interest:
            return JsonResponse({'success': False, 'error': 'Missing required fields: name, email, institution_name, plan_interest'}, status=400)

        if plan_interest not in ['institution', 'institution_annual', 'enterprise']:
            return JsonResponse({'success': False, 'error': 'Invalid plan_interest value'}, status=400)

        # Save to database first (critical - never lose the lead)
        inquiry = SalesInquiry.objects.create(
            name=name,
            email=email,
            institution_name=institution_name,
            phone=phone,
            plan_interest=plan_interest,
            message=message
        )

        # Send email notification (best-effort - failure should not block success response)
        try:
            subject = f"New Sales Inquiry: {plan_interest.replace('_', ' ').title()} - {institution_name}"
            body = f"""
New Sales Inquiry from Persona Pricing Page

Name: {name}
Email: {email}
Institution: {institution_name}
Phone: {phone or 'Not provided'}
Plan Interest: {plan_interest.replace('_', ' ').title()}

Message:
{message or 'No message provided'}

Submitted at: {inquiry.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=['harshit77.edu@gmail.com'],
                fail_silently=True  # Don't raise exception on email failure
            )
            logger.info(f"Sales inquiry email sent successfully for {email} - {institution_name}")
        except Exception as e:
            logger.error(f"Failed to send sales inquiry email for {email} - {institution_name}: {str(e)}")
            # Email failed but inquiry is saved - continue with success response

        return JsonResponse({
            'success': True,
            'message': 'Thanks! We\'ll be in touch within 1 business day.'
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON in request body'}, status=400)
    except Exception as e:
        logger.exception(f"Unexpected error in sales_inquiry: {str(e)}")
        return JsonResponse({'success': False, 'error': 'An unexpected error occurred. Please try again.'}, status=500)
