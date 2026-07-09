from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.db import models
from django.db.models import Avg, Max, Min, Sum, Count, Q, F
from django.core.paginator import Paginator
from django.utils import timezone
from django.conf import settings
import json
import csv
import uuid
import base64
from datetime import datetime, timedelta
from django.template.loader import get_template
from xhtml2pdf import pisa

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


# Import models
from .models import (
    JobRole, InterviewQuestion, AssessmentLink, Assessment, AssessmentResult,
    PlatformJobTitle, PlatformQuestion, IndividualAssessment, 
    IndividualAssessmentResponse, AssessmentSnapshot,
    BusinessAssessmentResponse, BusinessAssessmentSnapshot
)
from UserAPI.models import BusinessUser
from AnalysisModules.feedback_generator import (
    evaluate_answer_content,
    generate_feedback_summary,
    generate_improvement_roadmap,
    generate_tailored_questions,
)
from django_ratelimit.decorators import ratelimit
from .upload_validators import validate_audio_b64, validate_image_b64

# Import analysis modules with fallback
try:
    from AnalysisModules import (
        analyze_attire_base64, analyze_body_language_base64, analyze_speech,
        ATTIRE_ANALYSIS_AVAILABLE, BODY_LANGUAGE_ANALYSIS_AVAILABLE, SPEECH_ANALYSIS_AVAILABLE
    )
except ImportError:
    # Fallback functions if analysis modules not available
    def analyze_attire_base64(*args, **kwargs):
        return {"error": "Attire analysis not available"}
    def analyze_body_language_base64(*args, **kwargs):
        return {"error": "Body language analysis not available"}
    def analyze_speech(*args, **kwargs):
        return {"error": "Speech analysis not available"}
    
    ATTIRE_ANALYSIS_AVAILABLE = False
    BODY_LANGUAGE_ANALYSIS_AVAILABLE = False
    SPEECH_ANALYSIS_AVAILABLE = False


def _snapshot_score_from_data(snapshot):
    """Return a 0-10 score from snapshot column or nested analysis_result."""
    if snapshot.score is not None and snapshot.score > 0:
        return float(snapshot.score)

    data = snapshot.analysis_data or {}
    result = data.get('analysis_result', data)
    if not isinstance(result, dict):
        return None

    for key in ('overall_score', 'score', 'confidence_score', 'posture_score', 'attire_score'):
        val = result.get(key)
        if val is not None:
            try:
                score = float(val)
                if score <= 1.0:
                    score *= 10
                return score
            except (ValueError, TypeError):
                continue
    return None


def _enqueue_speech_analysis(response_id, audio_data, question_text):
    """Run speech analysis via django-q, falling back to a daemon thread."""
    from .tasks import run_speech_analysis_task

    try:
        from django_q.tasks import async_task
        async_task(run_speech_analysis_task, response_id, audio_data, question_text)
    except Exception as e:
        print(f"django-q enqueue failed ({e}), using thread fallback")
        import threading
        thread = threading.Thread(
            target=run_speech_analysis_task,
            args=(response_id, audio_data, question_text),
            daemon=True,
        )
        thread.start()


@login_required
def business_dashboard(request):
    """Main dashboard for business users to manage job roles and assessments"""
    if not hasattr(request.user, 'business_profile'):
        messages.error(request, "Access denied. Only business users can access this page.")
        return redirect('persona_frontend:home')
    
    business_user = request.user.business_profile
    job_roles = JobRole.objects.filter(business_user=business_user).order_by('-created_at')
    
    # Build candidate rankings per job role
    job_roles_with_rankings = []
    for role in job_roles:
        completed_assessments = Assessment.objects.filter(
            assessment_link__job_role=role,
            status='completed'
        ).select_related('result').order_by(F('result__overall_score').desc(nulls_last=True))
        
        job_roles_with_rankings.append({
            'role': role,
            'completed_assessments': completed_assessments,
            'has_multiple_submissions': completed_assessments.count() > 1
        })
    
    # Get recent assessments
    recent_assessments = Assessment.objects.filter(
        assessment_link__job_role__business_user=business_user
    ).order_by('-created_at')[:10]
    
    context = {
        'job_roles': job_roles,
        'job_roles_with_rankings': job_roles_with_rankings,
        'recent_assessments': recent_assessments,
        'total_roles': job_roles.count(),
        'total_assessments': Assessment.objects.filter(
            assessment_link__job_role__business_user=business_user
        ).count(),
    }
    return render(request, 'analysis/business_dashboard.html', context)


@login_required
def create_job_role(request):
    """Create a new job role"""
    if not hasattr(request.user, 'business_profile'):
        messages.error(request, "Access denied.")
        return redirect('persona_frontend:home')
    
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        
        if not title:
            messages.error(request, "Job title is required.")
            return render(request, 'analysis/create_job_role.html')
        
        try:
            with transaction.atomic():
                job_role = JobRole.objects.create(
                    business_user=request.user.business_profile,
                    title=title,
                    description=description
                )
                messages.success(request, f"Job role '{title}' created successfully!")
                return redirect('analysis:job_role_detail', job_role_id=job_role.id)
        except Exception as e:
            messages.error(request, f"Error creating job role: {str(e)}")
    
    return render(request, 'analysis/create_job_role.html')


@login_required
def job_role_detail(request, job_role_id):
    """View and manage a specific job role"""
    if not hasattr(request.user, 'business_profile'):
        messages.error(request, "Access denied.")
        return redirect('persona_frontend:home')
    
    job_role = get_object_or_404(
        JobRole, 
        id=job_role_id, 
        business_user=request.user.business_profile
    )
    
    # Get questions and assessment links
    questions = job_role.questions.all().order_by('created_at')
    assessment_links = job_role.assessment_links.all().order_by('-created_at')
    
    # Get assessments taken through these links
    assessments = Assessment.objects.filter(
        assessment_link__in=assessment_links
    ).order_by('-created_at')
    
    context = {
        'job_role': job_role,
        'questions': questions,
        'assessment_links': assessment_links,
        'assessments': assessments,
        'total_assessments': assessments.count(),
    }
    return render(request, 'analysis/job_role_detail.html', context)


@login_required
@require_http_methods(["POST"])
def add_question(request, job_role_id):
    """Add a question to a job role"""
    if not hasattr(request.user, 'business_profile'):
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    job_role = get_object_or_404(
        JobRole, 
        id=job_role_id, 
        business_user=request.user.business_profile
    )
    
    question_text = request.POST.get('question')
    question_type = request.POST.get('type', 'behavioral')
    
    if not question_text:
        return JsonResponse({'error': 'Question text is required'}, status=400)
    
    try:
        question = InterviewQuestion.objects.create(
            job_role=job_role,
            question_text=question_text,
            question_type=question_type
        )
        return JsonResponse({
            'success': True,
            'question': {
                'id': question.id,
                'question': question.question_text,
                'type': question.question_type
            }
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def generate_assessment_link(request, job_role_id):
    """Generate a new assessment link for a job role"""
    if not hasattr(request.user, 'business_profile'):
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    job_role = get_object_or_404(
        JobRole, 
        id=job_role_id, 
        business_user=request.user.business_profile
    )
    
    # Check if job role has questions
    if not job_role.questions.exists():
        return JsonResponse({
            'error': 'Cannot generate assessment link. Please add questions to this job role first.'
        }, status=400)
    
    try:
        assessment_link = AssessmentLink.objects.create(job_role=job_role)
        return JsonResponse({
            'success': True,
            'link': {
                'id': assessment_link.id,
                'access_code': assessment_link.access_code,
                'full_url': request.build_absolute_uri(f'/assessment/{assessment_link.unique_link}/'),
                'created_at': assessment_link.created_at.isoformat()
            }
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def assessment_results(request, job_role_id):
    """View assessment results for a job role"""
    if not hasattr(request.user, 'business_profile'):
        messages.error(request, "Access denied.")
        return redirect('persona_frontend:home')
    
    job_role = get_object_or_404(
        JobRole, 
        id=job_role_id, 
        business_user=request.user.business_profile
    )
    
    assessments = Assessment.objects.filter(
        assessment_link__job_role=job_role,
        status='completed'
    ).order_by('-completed_at')
    
    # Pagination
    paginator = Paginator(assessments, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'job_role': job_role,
        'page_obj': page_obj,
        'assessments': page_obj,
    }
    return render(request, 'analysis/assessment_results.html', context)


def take_assessment(request, link_id):
    """Public view for taking an assessment using the combined assessment system"""
    assessment_link = get_object_or_404(AssessmentLink, unique_link=link_id)
    
    if not assessment_link.is_active:
        return render(request, 'analysis/assessment_inactive.html', {
            'message': 'This assessment link is no longer active.'
        })
    
    # Get or create business assessment session
    session_key = f'business_assessment_{link_id}'
    session_id = request.session.get(session_key)
    
    if session_id:
        try:
            # Check if assessment exists and redirect to combined interface
            assessment = Assessment.objects.get(session_id=session_id, assessment_type='business')
            if assessment.status == 'completed':
                return redirect('analysis:business_assessment_complete', session_id=session_id)
            else:
                # Continue with existing assessment
                return redirect('analysis:business_combined_assessment', session_id=session_id)
        except Assessment.DoesNotExist:
            # Create new assessment
            pass
    
    # Create new business assessment
    assessment = Assessment.objects.create(
        assessment_link=assessment_link,
        assessment_type='business',
        job_title=assessment_link.job_role.title,
        status='in_progress'
    )
    
    # Store session
    request.session[session_key] = assessment.id
    
    # Redirect to combined assessment interface
    return redirect('analysis:business_combined_assessment', assessment_id=assessment.id)


def business_combined_assessment(request, assessment_id):
    """Combined business assessment interface (same as individual but for business)"""
    assessment = get_object_or_404(Assessment, id=assessment_id, assessment_type='business')
    
    if assessment.status == 'completed':
        return redirect('analysis:business_assessment_complete', assessment_id=assessment_id)
    
    # Get questions from the job role
    questions = assessment.assessment_link.job_role.questions.all().order_by('order', 'created_at')
    
    if not questions.exists():
        return render(request, 'analysis/assessment_error.html', {
            'error': 'No questions found for this assessment.'
        })
    
    # Get current progress
    answered_questions = assessment.responses.values_list('question_order', flat=True)
    total_questions = questions.count()
    current_question_number = len(answered_questions) + 1
    
    # Check if assessment is complete
    if current_question_number > total_questions:
        # Mark as completed and redirect to results
        assessment.status = 'completed'
        assessment.completed_at = timezone.now()
        assessment.save()
        return redirect('analysis:business_assessment_complete', assessment_id=assessment.id)
    
    # Get current question
    current_question = questions[current_question_number - 1]
    
    context = {
        'assessment': assessment,
        'current_question': current_question,
        'current_question_number': current_question_number,
        'total_questions': total_questions,
        'questions': questions,
        'job_title': assessment.assessment_link.job_role,
        'progress_percentage': int((current_question_number - 1) / total_questions * 100),
    }
    
    return render(request, 'analysis/business_combined_assessment.html', context)


def business_assessment_complete(request, assessment_id):
    """Business assessment results page (for recruiters)"""
    assessment = get_object_or_404(Assessment, id=assessment_id, assessment_type='business')
    
    if assessment.status != 'completed':
        return redirect('analysis:business_combined_assessment', assessment_id=assessment_id)
    
    # Calculate scores using the same logic as individual assessments
    responses = assessment.responses.all()
    snapshots = assessment.snapshots.all()
    
    # Calculate duration
    duration_seconds = 0
    if assessment.completed_at and assessment.started_at:
        duration_seconds = (assessment.completed_at - assessment.started_at).total_seconds()
    duration_minutes = duration_seconds / 60 if duration_seconds > 0 else 0
    
    # Calculate scores
    if assessment.status == 'completed' and not assessment.overall_score:
        # Calculate scores using the same logic as individual assessments
        if responses.exists():
            total_fluency = 0
            total_pronunciation = 0
            total_content = 0
            total_formality = 0
            total_confidence = 0
            valid_responses = 0
            
            for response in responses:
                speech_analysis = response.analysis_data.get('speech_analysis', {})
                if speech_analysis and not speech_analysis.get('error'):
                    fluency = speech_analysis.get('fluency_score', 0)
                    pronunciation = speech_analysis.get('pronunciation_score', 0)
                    content = speech_analysis.get('content_score', 0)
                    formality = speech_analysis.get('formality_score', 0)  
                    confidence = speech_analysis.get('confidence_score', 0)
                    
                    # Convert to 0-10 scale
                    if fluency and fluency <= 1:
                        fluency *= 10
                    if pronunciation and pronunciation <= 1:
                        pronunciation *= 10
                    if content and content <= 1:
                        content *= 10
                    if formality and formality <= 1:
                        formality *= 10
                    if confidence and confidence <= 1:
                        confidence *= 10
                    
                    total_fluency += fluency
                    total_pronunciation += pronunciation
                    total_content += content
                    total_formality += formality
                    total_confidence += confidence
                    valid_responses += 1
            
            if valid_responses > 0:
                assessment.speaking_score = (total_fluency + total_pronunciation + total_content + total_formality + total_confidence) / (5 * valid_responses)
        
        if snapshots.exists():
            # Use pre-calculated overall scores from analyzers
            body_language_snapshots = snapshots.filter(analysis_type='body_language')
            attire_snapshots = snapshots.filter(analysis_type='attire')
            
            # Calculate average body language score from snapshots
            if body_language_snapshots.exists():
                body_scores = []
                for snapshot in body_language_snapshots:
                    if snapshot.score and snapshot.score > 0:
                        body_scores.append(snapshot.score)
                
                if body_scores:
                    assessment.body_language_score = sum(body_scores) / len(body_scores)
                # If no valid scores, leave body_language_score as None (not a fake number)
            
            # Calculate average attire score from snapshots  
            if attire_snapshots.exists():
                attire_scores = []
                for snapshot in attire_snapshots:
                    if snapshot.score and snapshot.score > 0:
                        attire_scores.append(snapshot.score)
                
                if attire_scores:
                    assessment.attire_score = sum(attire_scores) / len(attire_scores)
                # If no valid scores, leave attire_score as None (not a fake number)
        
        # Calculate overall score
        scores = [s for s in [
            assessment.speaking_score,
            assessment.body_language_score,
            assessment.attire_score
        ] if s is not None]
        
        if scores:
            assessment.overall_score = sum(scores) / len(scores)
        
        assessment.save()
    
    context = {
        'assessment': assessment,
        'responses': responses,
        'job_title': assessment.assessment_link.job_role,
        'duration_minutes': duration_minutes,
        'duration_seconds': int(duration_seconds),
        'business_view': True,  # Flag to indicate this is for business users
    }
    
    return render(request, 'analysis/business_assessment_complete.html', context)


def business_capture_snapshot(request, assessment_id):
    """Capture analysis snapshots for business assessments"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    try:
        assessment = Assessment.objects.get(id=assessment_id, assessment_type='business')
        
        analysis_type = request.POST.get('analysis_type')
        image_data = request.POST.get('image_data')
        
        if not analysis_type or not image_data:
            return JsonResponse({'error': 'Missing analysis_type or image_data'}, status=400)
        
        if not image_data.startswith('data:image'):
            return JsonResponse({'error': 'Invalid image data format'}, status=400)
        
        # Extract base64 data
        image_data = image_data.split(',')[1]
        
        # Analyze based on type
        analysis_result = {}
        
        if analysis_type == 'body_language' and BODY_LANGUAGE_ANALYSIS_AVAILABLE:
            analysis_result = analyze_body_language_base64(image_data)
        elif analysis_type == 'attire' and ATTIRE_ANALYSIS_AVAILABLE:
            analysis_result = analyze_attire_base64(image_data, 'formal_business')
        else:
            analysis_result = {'error': f'{analysis_type} analysis not available'}
        
        # Get overall score and convert to 0-10 scale if needed
        overall_score = analysis_result.get('overall_score', 0)
        if overall_score and overall_score <= 1:
            overall_score *= 10
        
        # Create snapshot record
        snapshot = BusinessAssessmentSnapshot.objects.create(
            assessment=assessment,
            analysis_type=analysis_type,
            timestamp=timezone.now(),
            score=overall_score,
            analysis_data=analysis_result,
            feedback=', '.join(analysis_result.get('feedback', []))
        )
        
        return JsonResponse({
            'success': True,
            'snapshot_id': snapshot.id,
            'score': snapshot.score,
            'feedback': analysis_result.get('feedback', []),
            'analysis_available': analysis_type in ['body_language', 'attire']
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def business_submit_response(request, assessment_id):
    """Submit response for business assessment"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    try:
        assessment = Assessment.objects.get(id=assessment_id, assessment_type='business')
        
        question_order = int(request.POST.get('question_order', 0))
        audio_data = request.FILES.get('audio_data')
        
        if not question_order or not audio_data:
            return JsonResponse({'error': 'Missing question_order or audio_data'}, status=400)
        
        # Get the question
        questions = assessment.assessment_link.job_role.questions.all().order_by('order', 'created_at')
        if question_order > questions.count():
            return JsonResponse({'error': 'Invalid question order'}, status=400)
        
        question = questions[question_order - 1]
        
        # Create response record with initial data
        initial_analysis_data = {
            'timestamp': timezone.now().isoformat(),
            'question_text': question.question_text,
            'audio_file_size': audio_data.size,
            'speech_analysis_status': 'pending'
        }
        
        response = BusinessAssessmentResponse.objects.create(
            assessment=assessment,
            question_order=question_order,
            question_text=question.question_text,
            response_duration=0,  # Will be updated after speech analysis
            analysis_data=initial_analysis_data
        )
        
        # Process speech analysis in background (same as individual assessments)
        if SPEECH_ANALYSIS_AVAILABLE:
            try:
                def process_speech_analysis():
                    try:
                        # Save audio file temporarily
                        import tempfile
                        import os
                        
                        # IMPORTANT: use .webm because MediaRecorder produces WebM/Opus
                        # regardless of the Blob MIME type hint given in the frontend.
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_file:
                            for chunk in audio_data.chunks():
                                temp_file.write(chunk)
                            temp_file_path = temp_file.name
                        
                        # Read bytes and perform speech analysis
                        with open(temp_file_path, 'rb') as f:
                            audio_bytes = f.read()
                        
                        # Perform speech analysis (expects bytes, not a file path)
                        speech_analysis = analyze_speech(audio_bytes)
                        
                        # Clean up temp file
                        os.unlink(temp_file_path)
                        
                        # Update response with analysis results
                        response.analysis_data = {
                            **initial_analysis_data,
                            'speech_analysis': speech_analysis,
                            'speech_analysis_status': 'completed'
                        }
                        response.save()
                        
                    except Exception as e:
                        # Update response with error
                        response.analysis_data = {
                            **initial_analysis_data,
                            'speech_analysis': {'error': str(e)},
                            'speech_analysis_status': 'error'
                        }
                        response.save()
                
                # Run in background thread
                import threading
                thread = threading.Thread(target=process_speech_analysis)
                thread.daemon = True
                thread.start()
                
            except Exception as e:
                # Update with error if threading fails
                response.analysis_data = {
                    **initial_analysis_data,
                    'speech_analysis': {'error': str(e)},
                    'speech_analysis_status': 'error'
                }
                response.save()
        else:
            response.analysis_data = {
                **initial_analysis_data,
                'speech_analysis_status': 'not_available'
            }
            response.save()
        
        return JsonResponse({
            'success': True,
            'response_id': response.id
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def assessment_complete(request, assessment_id):
    """Show completion page after assessment"""
    assessment = get_object_or_404(Assessment, id=assessment_id)
    
    context = {
        'assessment': assessment,
        'job_role': assessment.assessment_link.job_role,
    }
    return render(request, 'analysis/assessment_complete.html', context)


# =====================================
# INDIVIDUAL ASSESSMENT VIEWS
# =====================================

def _resume_session_key(session_id):
    return f'individual_assessment_resume_text_{session_id}'


def _validate_resume_upload(resume_file):
    if not resume_file:
        return True, None

    name = resume_file.name.lower()
    if not (name.endswith('.pdf') or name.endswith('.txt')):
        return False, 'Resume must be a PDF or plain text file.'

    max_size = getattr(settings, 'MAX_RESUME_UPLOAD_MB', 5) * 1024 * 1024
    if resume_file.size > max_size:
        return False, f'Resume must be smaller than {getattr(settings, "MAX_RESUME_UPLOAD_MB", 5)}MB.'

    return True, None


def _extract_resume_text(resume_file):
    file_name = resume_file.name.lower()
    content_type = getattr(resume_file, 'content_type', '') or ''

    resume_file.seek(0)
    if file_name.endswith('.pdf') or 'pdf' in content_type:
        if PdfReader is None:
            raise RuntimeError('PDF resume extraction requires the pypdf package.')
        reader = PdfReader(resume_file)
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text() or ''
            text_parts.append(page_text)
        return '\n'.join(text_parts).strip()

    if file_name.endswith('.txt') or content_type.startswith('text/'):
        raw = resume_file.read()
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8', errors='ignore')
        return raw.strip()

    raise ValueError('Unsupported resume format. Please upload a PDF or plain text file.')


def individual_dashboard(request):
    """Dashboard for individual users to practice assessments"""
    if hasattr(request.user, 'business_profile'):
        messages.error(request, "Access denied. This section is for individual users only.")
        return redirect('analysis:business_dashboard')
    
    # Get user's recent assessments
    recent_assessments = IndividualAssessment.objects.filter(
        user=request.user
    ).order_by('-created_at')[:5]
    
    # Get available job titles with active question counts
    job_titles = PlatformJobTitle.objects.filter(is_active=True).annotate(
        active_question_count=Count('questions', filter=Q(questions__is_active=True))
    ).order_by('title')
    
    # Analysis module availability
    analysis_status = {
        'attire_available': ATTIRE_ANALYSIS_AVAILABLE,
        'body_language_available': BODY_LANGUAGE_ANALYSIS_AVAILABLE,
        'speech_available': SPEECH_ANALYSIS_AVAILABLE,
    }
    
    # Chart data for completed assessments
    completed_assessments = IndividualAssessment.objects.filter(
        user=request.user, 
        status='completed', 
        overall_score__isnull=False
    ).order_by('completed_at')
    
    chart_dates = []
    chart_scores = []
    for a in completed_assessments:
        if a.completed_at:
            chart_dates.append(a.completed_at.strftime('%b %d'))
            chart_scores.append(float(a.overall_score))
            
    chart_data = {
        'labels': chart_dates,
        'scores': chart_scores
    }
    
    context = {
        'recent_assessments': recent_assessments,
        'job_titles': job_titles,
        'analysis_status': analysis_status,
        'chart_json': json.dumps(chart_data),
    }
    return render(request, 'analysis/individual_dashboard.html', context)


@login_required
def start_individual_assessment(request):
    """Start a new individual assessment"""
    if request.method == 'POST':
        job_title_id = request.POST.get('job_title_id')
        
        if not job_title_id:
            messages.error(request, "Please select a job title.")
            return redirect('analysis:individual_dashboard')
        
        try:
            job_title = PlatformJobTitle.objects.get(id=job_title_id, is_active=True)

            # Terminate any previous incomplete sessions for this user
            IndividualAssessment.objects.filter(
                user=request.user,
                status__in=['pending', 'in_progress']
            ).update(status='terminated')

            # Create new assessment
            assessment = IndividualAssessment.objects.create(
                user=request.user,
                platform_job_title=job_title,
                status='pending'
            )
            
            messages.success(request, f"Assessment for {job_title.title} has been created!")
            return redirect('analysis:individual_assessment_setup', session_id=assessment.session_id)
            
        except PlatformJobTitle.DoesNotExist:
            messages.error(request, "Invalid job title selected.")
            return redirect('analysis:individual_dashboard')
    
    return redirect('analysis:individual_dashboard')


@login_required
def individual_assessment_setup(request, session_id):
    """Setup page for individual assessment with system requirements"""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user,
        status='pending'
    )
    
    # Select questions for this assessment if not already done
    if not assessment.selected_questions:
        assessment.select_questions()
        # Reload to get the updated total_questions
        assessment.refresh_from_db()
    
    resume_key = _resume_session_key(session_id)
    resume_uploaded = bool(request.session.get(resume_key))
    
    # Ensure we show the actual number of selected questions, not the pool size
    actual_question_count = len(assessment.selected_questions) if assessment.selected_questions else 0
    
    context = {
        'assessment': assessment,
        'job_title': assessment.platform_job_title,
        'total_questions': actual_question_count,
        'question_count_display': actual_question_count,
        'estimated_duration': assessment.estimated_duration // 60,  # Convert to minutes
        'resume_uploaded': resume_uploaded,
        'analysis_status': {
            'attire_available': ATTIRE_ANALYSIS_AVAILABLE,
            'body_language_available': BODY_LANGUAGE_ANALYSIS_AVAILABLE,
            'speech_available': SPEECH_ANALYSIS_AVAILABLE,
        }
    }
    return render(request, 'analysis/individual_assessment_setup.html', context)


@login_required
def start_individual_assessment_session(request, session_id):
    """Start the actual assessment session, optionally processing an uploaded resume."""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user,
        status='pending'
    )

    resume_text = None
    if request.method == 'POST':
        resume_file = request.FILES.get('resume')
        if resume_file:
            is_valid, error = _validate_resume_upload(resume_file)
            if not is_valid:
                messages.error(request, error)
                return redirect('analysis:individual_assessment_setup', session_id=session_id)
            try:
                resume_text = _extract_resume_text(resume_file)
                if resume_text:
                    resume_text = resume_text[:20000]
                    request.session[_resume_session_key(session_id)] = resume_text
                    request.session.modified = True
            except Exception as exc:
                messages.error(request, f'Resume upload failed: {exc}')
                return redirect('analysis:individual_assessment_setup', session_id=session_id)

    resume_key = _resume_session_key(session_id)
    stored_resume_text = request.session.get(resume_key)

    if not assessment.selected_questions:
        if stored_resume_text:
            tailored_questions = generate_tailored_questions(
                resume_text=stored_resume_text,
                job_role=assessment.platform_job_title.title,
                num_questions=5,
            )
            if tailored_questions:
                created_question_ids = []
                next_order = PlatformQuestion.objects.filter(
                    job_title=assessment.platform_job_title
                ).aggregate(models.Max('order'))['order__max'] or 0
                for text in tailored_questions:
                    next_order += 1
                    question = PlatformQuestion.objects.create(
                        job_title=assessment.platform_job_title,
                        question_text=text,
                        question_type='general',
                        is_mandatory=False,
                        difficulty_level='intermediate',
                        expected_duration=120,
                        order=next_order,
                        is_active=False,
                    )
                    created_question_ids.append(question.id)
                assessment.selected_questions = created_question_ids
                assessment.total_questions = len(created_question_ids)
                assessment.save()
            else:
                assessment.select_questions()
        else:
            assessment.select_questions()

        if stored_resume_text:
            try:
                del request.session[resume_key]
                request.session.modified = True
            except KeyError:
                pass

    assessment.status = 'in_progress'
    assessment.started_at = timezone.now()
    assessment.save()

    return redirect('analysis:individual_assessment_question', session_id=session_id)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def abandon_assessment(request, session_id):
    """Mark an in-progress assessment as terminated (called via sendBeacon on page unload)"""
    try:
        updated = IndividualAssessment.objects.filter(
            session_id=session_id,
            user=request.user,
            status='in_progress'
        ).update(status='terminated')
        if updated:
            return JsonResponse({'success': True, 'terminated': True})
        return JsonResponse({'success': True, 'terminated': False})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def combined_assessment(request, session_id):
    """Combined setup and assessment page with all questions"""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user,
        status__in=['pending', 'in_progress']
    )
    
    # Update status to in_progress when assessment starts
    if assessment.status == 'pending':
        assessment.status = 'in_progress'
        assessment.started_at = timezone.now()
        assessment.save()
    
    # Get all questions for this assessment
    if assessment.selected_questions:
        questions = []
        for question_id in assessment.selected_questions:
            try:
                questions.append(PlatformQuestion.objects.get(id=question_id))
            except PlatformQuestion.DoesNotExist:
                continue
    else:
        questions = list(
            assessment.platform_job_title.questions.filter(is_active=True).order_by('?')
        )
    
    # Prepare questions data for JavaScript
    questions_data = []
    for question in questions:
        questions_data.append({
            'id': question.id,
            'question_text': question.question_text,
            'question_type': question.question_type,
            'question_type_display': question.get_question_type_display(),
            'is_mandatory': question.is_mandatory,
            'time_limit': 15  # Fixed 15 seconds for thinking time
        })
    
    context = {
        'assessment': assessment,
        'session_id': session_id,
        'questions_json': json.dumps(questions_data),
        'total_questions': len(questions),
        'analysis_status': {
            'attire_available': ATTIRE_ANALYSIS_AVAILABLE,
            'body_language_available': BODY_LANGUAGE_ANALYSIS_AVAILABLE,
            'speech_available': SPEECH_ANALYSIS_AVAILABLE,
        }
    }
    return render(request, 'analysis/combined_assessment.html', context)


@login_required
def individual_assessment_question(request, session_id):
    """Display current question for individual assessment"""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user,
        status='in_progress'
    )
    
    # Get current question
    current_question = assessment.get_next_question()
    
    if not current_question:
        # No more questions, complete the assessment
        return redirect('analysis:complete_individual_assessment', session_id=session_id)
    
    context = {
        'assessment': assessment,
        'question': current_question,
        'question_number': assessment.current_question_index + 1,
        'total_questions': assessment.total_questions,
        'progress_percentage': ((assessment.current_question_index + 1) / assessment.total_questions) * 100,
        'session_id': session_id,
        'analysis_status': {
            'attire_available': ATTIRE_ANALYSIS_AVAILABLE,
            'body_language_available': BODY_LANGUAGE_ANALYSIS_AVAILABLE,
            'speech_available': SPEECH_ANALYSIS_AVAILABLE,
        }
    }
    return render(request, 'analysis/individual_assessment_question.html', context)


@require_http_methods(["POST"])
@ratelimit(key='user', rate=settings.RATE_LIMIT_SUBMISSION, block=True)
def submit_assessment_response(request, session_id):
    """Submit response for current question and move to next"""
    try:
        assessment = get_object_or_404(
            IndividualAssessment,
            session_id=session_id,
            user=request.user,
            status='in_progress'
        )
        
        # Get current question
        current_question = assessment.get_next_question()
        if not current_question:
            return JsonResponse({'error': 'No current question'}, status=400)
        
        # Parse request data
        data = json.loads(request.body)
        
        # Handle skip
        if data.get('skipped'):
            IndividualAssessmentResponse.objects.create(
                assessment=assessment,
                question=current_question,
                question_order=assessment.current_question_index + 1,
                question_started_at=timezone.now(),
                response_started_at=timezone.now(),
                response_ended_at=timezone.now(),
                response_duration=0,
                time_to_start=0,
                analysis_data={
                    'skipped': True,
                    'skip_reason': data.get('skip_reason', 'user_skipped'),
                    'fullscreen_violations': data.get('fullscreen_violations', 0),
                }
            )
            assessment.current_question_index += 1
            assessment.save()
            is_complete = assessment.current_question_index >= assessment.total_questions
            return JsonResponse({
                'success': True,
                'is_complete': is_complete,
                'next_question_url': f'/analysis/individual/{session_id}/question/' if not is_complete else None,
                'complete_url': f'/analysis/individual/{session_id}/complete/' if is_complete else None,
            })

        # Create response record
        response = IndividualAssessmentResponse.objects.create(
            assessment=assessment,
            question=current_question,
            question_order=assessment.current_question_index + 1,
            question_started_at=timezone.now(),
            response_started_at=timezone.now(),
            response_ended_at=timezone.now(),
            response_duration=data.get('response_duration', 0),
            time_to_start=data.get('time_to_start', 0)
        )
        
        # Process audio if provided
        if 'audio_data' in data and data['audio_data']:
            is_valid, error_msg = validate_audio_b64(data['audio_data'])
            if not is_valid:
                return JsonResponse({'error': error_msg}, status=400)
            try:
                # Decode base64 audio
                audio_data = base64.b64decode(data['audio_data'].split(',')[1])
                
                # Save audio file
                filename = f"response_{assessment.id}_{response.question_order}_{uuid.uuid4().hex[:8]}.wav"
                # In production, save to proper media storage
                # For now, we'll process but not save
                
                # Analyze speech if available
                if SPEECH_ANALYSIS_AVAILABLE:
                    speech_analysis = analyze_speech(
                        audio_data, 
                        current_question.question_text,
                        data.get('response_duration', 0)
                    )
                    
                    response.response_text = speech_analysis.get('transcription', '')
                    response.fluency_score = speech_analysis.get('fluency_score', 0)
                    response.pronunciation_score = speech_analysis.get('pronunciation_score', 0)
                    response.relevance_score = speech_analysis.get('content_score', 0)
                    response.confidence_score = speech_analysis.get('confidence_score', 0)
                    response.analysis_data = {
                        'speech_analysis': speech_analysis,
                        'content_evaluation': evaluate_answer_content(
                            question_text=current_question.question_text,
                            transcript=speech_analysis.get('transcription', ''),
                            ideal_answer_points=current_question.ideal_answer_points,
                        ),
                    }
                    
            except Exception as e:
                print(f"Audio processing error: {e}")
        
        response.save()
        
        # Move to next question
        assessment.current_question_index += 1
        assessment.save()
        
        # Check if assessment is complete
        is_complete = assessment.current_question_index >= assessment.total_questions
        
        return JsonResponse({
            'success': True,
            'is_complete': is_complete,
            'next_question_url': f'/analysis/individual/{session_id}/question/' if not is_complete else None,
            'complete_url': f'/analysis/individual/{session_id}/complete/' if is_complete else None
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
@ratelimit(key='user', rate=settings.RATE_LIMIT_SNAPSHOT, block=True)
def capture_assessment_snapshot(request, session_id):
    """Capture and analyze webcam snapshot during assessment"""
    try:
        assessment = get_object_or_404(
            IndividualAssessment,
            session_id=session_id,
            user=request.user,
            status='in_progress'
        )
        
        data = json.loads(request.body)
        analysis_type = data.get('analysis_type', 'body_language')
        image_data = data.get('image_data', '')
        
        if not image_data:
            return JsonResponse({'error': 'No image data provided'}, status=400)
            
        is_valid, error_msg = validate_image_b64(image_data)
        if not is_valid:
            return JsonResponse({'error': error_msg}, status=400)
        
        # Analyze based on type
        analysis_result = {}
        
        if analysis_type == 'body_language' and BODY_LANGUAGE_ANALYSIS_AVAILABLE:
            analysis_result = analyze_body_language_base64(image_data)
        elif analysis_type == 'attire' and ATTIRE_ANALYSIS_AVAILABLE:
            analysis_result = analyze_attire_base64(image_data, 'formal_business')
        else:
            analysis_result = {'error': f'{analysis_type} analysis not available'}
        
        # Get overall score and convert to 0-10 scale if needed
        overall_score = analysis_result.get('overall_score', 0)
        if overall_score and overall_score <= 1:
            overall_score *= 10
        
        # Create snapshot record
        snapshot = AssessmentSnapshot.objects.create(
            assessment=assessment,
            analysis_type=analysis_type,
            timestamp=timezone.now(),
            score=overall_score,
            analysis_data=analysis_result,
            feedback=', '.join(analysis_result.get('feedback', []))
        )
        
        return JsonResponse({
            'success': True,
            'snapshot_id': snapshot.id,
            'score': snapshot.score,
            'feedback': analysis_result.get('feedback', []),
            'analysis_available': analysis_type in ['body_language', 'attire']
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@ratelimit(key='user', rate=settings.RATE_LIMIT_COMPLETION, block=True)
def complete_individual_assessment(request, session_id):
    """Complete the individual assessment and show results"""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user
    )
    
    responses = assessment.responses.all().order_by('question_order')
    
    # BUG FIX: Escalate tasks that have been 'pending' for more than 10 minutes to 'failed'.
    # Without this, a qcluster timeout/crash leaves the status stuck on 'pending' forever.
    _PROCESSING_TIMEOUT_SECONDS = 600  # 10 minutes
    now = timezone.now()
    for r in responses:
        if r.analysis_data.get('speech_analysis_status') == 'pending':
            age = (now - r.created_at).total_seconds()
            if age > _PROCESSING_TIMEOUT_SECONDS:
                r.analysis_data['speech_analysis_status'] = 'failed'
                r.analysis_data['speech_analysis'] = {
                    'error': f'Processing timed out after {int(age)}s — task may have crashed in qcluster.',
                    'transcription': '',
                    'word_count': 0,
                }
                r.save(update_fields=['analysis_data'])
                print(f"[Timeout] Escalated response {r.id} from 'pending' to 'failed' after {int(age)}s")
    
    # Re-fetch responses after potential timeout escalation
    responses = assessment.responses.all().order_by('question_order')
    
    # Check if any responses are still processing speech analysis
    if any(r.analysis_data.get('speech_analysis_status') == 'pending' for r in responses):
        context = {
            'assessment': assessment,
            'session_id': session_id,
        }
        return render(request, 'analysis/processing_results.html', context)

    needs_scoring = (
        assessment.status != 'completed'
        or assessment.overall_score is None
        or (
            assessment.snapshots.exists()
            and assessment.body_language_score is None
            and assessment.attire_score is None
        )
    )

    if needs_scoring:
        if assessment.status != 'completed':
            assessment.status = 'completed'
            assessment.completed_at = timezone.now()
            
            # Update user streak on completion
            if hasattr(request.user, 'individual_profile'):
                request.user.individual_profile.update_streak()
        
        # Calculate overall scores
        snapshots = assessment.snapshots.all()
        
        if responses.exists():
            # Calculate average speaking scores from analysis_data
            total_fluency = 0
            total_pronunciation = 0
            total_content = 0
            total_formality = 0
            total_confidence = 0
            valid_responses = 0
            
            for response in responses:
                speech_analysis = response.analysis_data.get('speech_analysis', {})
                if speech_analysis and not speech_analysis.get('error'):
                    # Speech analyzer returns scores in 0-1 range
                    fluency = speech_analysis.get('fluency_score', 0)
                    pronunciation = speech_analysis.get('pronunciation_score', 0)
                    content = speech_analysis.get('content_score', 0)
                    formality = speech_analysis.get('formality_score', 0)
                    confidence = speech_analysis.get('confidence_score', 0)
                    
                    # Convert to 0-10 scale
                    if fluency and fluency <= 1:
                        fluency *= 10
                    if pronunciation and pronunciation <= 1:
                        pronunciation *= 10
                    if content and content <= 1:
                        content *= 10
                    if formality and formality <= 1:
                        formality *= 10
                    if confidence and confidence <= 1:
                        confidence *= 10
                    
                    total_fluency += fluency
                    total_pronunciation += pronunciation
                    total_content += content
                    total_formality += formality
                    total_confidence += confidence
                    valid_responses += 1
            
            if valid_responses > 0:
                assessment.speaking_score = (total_fluency + total_pronunciation + total_content + total_formality + total_confidence) / (5 * valid_responses)
                
                # Calculate voice confidence score from voice_confidence analysis
                voice_confidence_scores = []
                for response in responses:
                    voice_conf_data = response.analysis_data.get('voice_confidence', {}) if isinstance(response.analysis_data, dict) else {}
                    if voice_conf_data and not voice_conf_data.get('error'):
                        vc_score = voice_conf_data.get('score', 0)
                        if vc_score and vc_score > 0:
                            voice_confidence_scores.append(vc_score)
                
                if voice_confidence_scores:
                    assessment.voice_confidence_score = sum(voice_confidence_scores) / len(voice_confidence_scores)
        
        if snapshots.exists():
            # Use pre-calculated overall scores from analyzers (already converted to 0-10 scale)
            body_language_snapshots = snapshots.filter(analysis_type='body_language')
            attire_snapshots = snapshots.filter(analysis_type='attire')
            
            # Calculate average body language score from snapshots
            if body_language_snapshots.exists():
                body_scores = []
                for snapshot in body_language_snapshots:
                    score = _snapshot_score_from_data(snapshot)
                    if score is not None and score > 0:
                        body_scores.append(score)
                        if snapshot.score is None:
                            snapshot.score = score
                            snapshot.save(update_fields=['score'])
                
                if body_scores:
                    assessment.body_language_score = sum(body_scores) / len(body_scores)
            
            # Calculate average attire score from snapshots  
            if attire_snapshots.exists():
                attire_scores = []
                for snapshot in attire_snapshots:
                    score = _snapshot_score_from_data(snapshot)
                    if score is not None and score > 0:
                        attire_scores.append(score)
                        if snapshot.score is None:
                            snapshot.score = score
                            snapshot.save(update_fields=['score'])
                
                if attire_scores:
                    assessment.attire_score = sum(attire_scores) / len(attire_scores)
        
        # Calculate overall score (keep individual scores for reference)
        scores = [s for s in [
            assessment.speaking_score,
            assessment.body_language_score,
            assessment.attire_score
        ] if s is not None]
        
        if scores:
            assessment.overall_score = sum(scores) / len(scores)
        
        assessment.save()
    
    # Get detailed results
    responses = assessment.responses.all().order_by('question_order')
    snapshots = assessment.snapshots.all().order_by('timestamp')

    per_question_evaluations = []
    for response in responses:
        analysis_data = response.analysis_data or {}
        evaluation = analysis_data.get('content_evaluation', {}) if isinstance(analysis_data, dict) else {}
        if evaluation:
            per_question_evaluations.append({
                'question_text': response.question.question_text,
                'content_correctness_score': evaluation.get('content_correctness_score'),
                'explanation': evaluation.get('explanation', ''),
            })

    ai_feedback_summary = generate_feedback_summary(
        {
            'overall_score': assessment.overall_score,
            'body_language_score': assessment.body_language_score,
            'attire_score': assessment.attire_score,
            'speaking_score': assessment.speaking_score,
        },
        per_question_evaluations,
    )
    
    # Generate improvement roadmap based on confirmed metrics
    speech_details = {}
    if responses.exists():
        first_resp_data = responses.first().analysis_data
        if isinstance(first_resp_data, dict):
            speech_details = first_resp_data.get('speech_analysis', {})

    improvement_roadmap = generate_improvement_roadmap(
        {
            'overall_score': assessment.overall_score,
            'body_language_score': assessment.body_language_score,
            'attire_score': assessment.attire_score,
            'speaking_score': assessment.speaking_score,
        },
        speech_details
    )
    
    # Save the generated roadmap back to the database
    if improvement_roadmap:
        assessment.improvement_roadmap = improvement_roadmap
        assessment.save(update_fields=['improvement_roadmap'])

    # ── Per-question confidence / energy chart data ─────────────────────
    # Extract the audio features already calculated by speech_analyzer.py
    # from each response's analysis_data['speech_analysis'] dict.
    chart_labels = []        # ["Q1", "Q2", ...]
    energy_data = []         # avg_energy per question (normalised 0-100)
    speaking_rate_data = []  # speaking_rate (onsets/sec) per question
    pitch_variance_data = [] # pitch_variance (normalised) per question

    for resp in responses:
        q_label = f"Q{resp.question_order}"
        ad = resp.analysis_data if isinstance(resp.analysis_data, dict) else {}
        sa = ad.get('speech_analysis', {})

        # All three values default to None when speech analysis wasn't run
        # (skipped / no audio) so we still show the label with a null point.
        # speaking_rate is at top-level of speech_analysis; avg_energy and
        # pitch_variance are nested inside details.audio_features.
        audio_features = sa.get('details', {}).get('audio_features', {})
        avg_energy    = audio_features.get('avg_energy')    # float, typically 0-0.3 (raw RMS)
        speaking_rate = sa.get('speaking_rate')             # onsets / second, e.g. 2-8
        pitch_var     = audio_features.get('pitch_variance') # Hz², can be large

        # Normalise energy to 0-100 scale (raw RMS values are 0–~0.5)
        if avg_energy is not None:
            avg_energy = round(min(avg_energy * 300, 100), 2)

        # Normalise pitch_variance: log-compress then map to 0-100
        if pitch_var is not None and pitch_var > 0:
            import math
            pitch_var = round(min(math.log1p(pitch_var) / 15 * 100, 100), 2)
        elif pitch_var == 0:
            pitch_var = 0

        chart_labels.append(q_label)
        energy_data.append(avg_energy)
        speaking_rate_data.append(round(speaking_rate, 2) if speaking_rate is not None else None)
        pitch_variance_data.append(pitch_var)

    # Rule-based plain-language interpretation
    energy_insight = ""
    valid_energy = [(i, v) for i, v in enumerate(energy_data) if v is not None]
    if len(valid_energy) >= 2:
        min_idx, min_val = min(valid_energy, key=lambda x: x[1])
        max_idx, max_val = max(valid_energy, key=lambda x: x[1])
        q_min = chart_labels[min_idx]
        q_max = chart_labels[max_idx]
        drop = max_val - min_val
        if drop > 15:
            energy_insight = (
                f"Your vocal energy was highest on {q_max} and dropped noticeably on {q_min}. "
                "This often happens with more complex or unexpected questions — it's a great area to practise "
                "staying energised throughout."
            )
        elif drop > 5:
            energy_insight = (
                f"Your energy was fairly consistent across questions, with a slight dip on {q_min}. "
                "Overall this shows good stamina — keep it up!"
            )
        else:
            energy_insight = (
                "Your vocal energy was consistent across all questions — a strong sign of sustained confidence."
            )
    elif len(valid_energy) == 1:
        energy_insight = "Energy data was captured for one question. Complete multi-question assessments to see trends."

    import json as _json
    confidence_chart_json = _json.dumps({
        'labels': chart_labels,
        'energy': energy_data,
        'speaking_rate': speaking_rate_data,
        'pitch_variance': pitch_variance_data,
    })

    # Get platform average for peer comparison
    platform_average = IndividualAssessment.get_platform_average_for_job(assessment.platform_job_title.id)
    
    context = {
        'assessment': assessment,
        'job_title': assessment.platform_job_title,
        'responses': responses,
        'snapshots': snapshots,
        'ai_feedback_summary': ai_feedback_summary,
        'duration_seconds': int((assessment.completed_at - assessment.started_at).total_seconds()) if assessment.completed_at and assessment.started_at else 0,
        'duration_minutes': int((assessment.completed_at - assessment.started_at).total_seconds() // 60) if assessment.completed_at and assessment.started_at else 0,
        'confidence_chart_json': confidence_chart_json,
        'energy_insight': energy_insight,
        'has_chart_data': bool(valid_energy),
        'platform_average': platform_average,
    }
    return render(request, 'analysis/individual_assessment_complete.html', context)


@login_required
def download_assessment_report(request, session_id):
    """Generate and download PDF report for an individual assessment"""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user
    )
    
    responses = assessment.responses.all().order_by('question_order')
    
    per_question_evaluations = []
    for response in responses:
        analysis_data = response.analysis_data or {}
        evaluation = analysis_data.get('content_evaluation', {}) if isinstance(analysis_data, dict) else {}
        if evaluation:
            # Get a brief transcript snippet
            speech = analysis_data.get('speech_analysis', {})
            transcript = speech.get('transcript', '') if isinstance(speech, dict) else ''
            
            per_question_evaluations.append({
                'question_text': response.question.question_text,
                'content_correctness_score': evaluation.get('content_correctness_score'),
                'explanation': evaluation.get('explanation', ''),
                'transcript': transcript[:200] + '...' if len(transcript) > 200 else transcript
            })

    ai_feedback_summary = generate_feedback_summary(
        {
            'overall_score': assessment.overall_score,
            'body_language_score': assessment.body_language_score,
            'attire_score': assessment.attire_score,
            'speaking_score': assessment.speaking_score,
        },
        per_question_evaluations,
    )
    
    context = {
        'assessment': assessment,
        'job_title': assessment.platform_job_title,
        'responses': responses,
        'ai_feedback_summary': ai_feedback_summary,
        'per_question_evaluations': per_question_evaluations,
        'duration_minutes': int((assessment.completed_at - assessment.started_at).total_seconds() // 60) if assessment.completed_at and assessment.started_at else 0,
    }
    
    template = get_template('analysis/assessment_pdf_report.html')
    html = template.render(context)
    
    response = HttpResponse(content_type='application/pdf')
    filename = f"assessment_report_{assessment.created_at.strftime('%Y%m%d')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse('We had some errors generating your PDF <pre>' + html + '</pre>')
    return response

@login_required
def assessment_history(request):
    """View assessment history with progress comparison dashboard."""
    if hasattr(request.user, 'business_profile'):
        return redirect('analysis:business_dashboard')

    all_assessments = IndividualAssessment.objects.filter(
        user=request.user
    ).order_by('-created_at').select_related('platform_job_title')

    completed = all_assessments.filter(status='completed')

    # ── Aggregate stats ────────────────────────────────────────────────────
    # Filter to only assessments with scores for aggregation
    completed_with_scores = completed.filter(overall_score__isnull=False)
    
    stats = completed_with_scores.aggregate(
        avg_score=Avg('overall_score'),
        best_score=Max('overall_score'),
        worst_score=Min('overall_score'),
        total=Count('id'),
    )
    avg_score  = round(stats['avg_score'],  1) if stats['avg_score']  else None
    best_score = round(stats['best_score'], 1) if stats['best_score'] else None
    total_completed = completed.count()

    # Total practice time (minutes)
    total_minutes = 0
    for a in completed:
        if a.completed_at and a.started_at:
            total_minutes += (a.completed_at - a.started_at).total_seconds() / 60
    total_minutes = round(total_minutes)

    # ── Trend: compare most-recent vs previous overall score ──────────────
    recent_two = list(completed_with_scores.order_by('-completed_at')[:2])
    trend = None
    trend_delta = None
    if len(recent_two) == 2:
        trend_delta = round(recent_two[0].overall_score - recent_two[1].overall_score, 1)
        trend = 'up' if trend_delta > 0 else ('down' if trend_delta < 0 else 'neutral')

    # ── Chart data: score progression over time, grouped by role ──────────
    chart_points = []
    for a in reversed(list(completed_with_scores.order_by('completed_at'))):
        chart_points.append({
            'date': a.completed_at.strftime('%d %b %Y') if a.completed_at else '',
            'role': a.platform_job_title.title,
            'overall':       round(a.overall_score, 1)       if a.overall_score       else None,
            'speaking':      round(a.speaking_score, 1)      if a.speaking_score      else None,
            'body_language': round(a.body_language_score, 1) if a.body_language_score else None,
            'attire':        round(a.attire_score, 1)        if a.attire_score        else None,
        })

    # ── Per-role breakdown ─────────────────────────────────────────────────
    role_stats = {}
    for a in completed_with_scores:
        role = a.platform_job_title.title
        if role not in role_stats:
            role_stats[role] = {'scores': [], 'count': 0, 'best': None}
        role_stats[role]['scores'].append(a.overall_score)
        role_stats[role]['count'] += 1
        if role_stats[role]['best'] is None or a.overall_score > role_stats[role]['best']:
            role_stats[role]['best'] = a.overall_score
    for role in role_stats:
        scores = role_stats[role]['scores']
        role_stats[role]['avg'] = round(sum(scores) / len(scores), 1)
        role_stats[role]['best'] = round(role_stats[role]['best'], 1)

    # ── Pagination ────────────────────────────────────────────────────────
    paginator = Paginator(all_assessments, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'total_assessments': all_assessments.count(),
        'total_completed': total_completed,
        'avg_score': avg_score,
        'best_score': best_score,
        'total_minutes': total_minutes,
        'trend': trend,
        'trend_delta': trend_delta,
        'chart_data_json': json.dumps(chart_points),
        'role_stats': role_stats,
        'has_chart_data': len(chart_points) >= 2,
    }
    return render(request, 'analysis/assessment_history.html', context)


@login_required
def clean_assessment_question(request, session_id):
    """Clean, optimized assessment interface"""
    try:
        assessment = get_object_or_404(
            IndividualAssessment, 
            session_id=session_id,
            individual_user=request.user.individual_profile
        )
        
        # Get current question or next question
        answered_questions = IndividualAssessmentResponse.objects.filter(
            assessment=assessment
        ).values_list('question_id', flat=True)
        
        # Get available questions for this job title
        all_questions = PlatformQuestion.objects.filter(
            job_title=assessment.platform_job_title
        ).order_by('is_mandatory', '?')  # Mandatory first, then random
        
        # Get next unanswered question
        current_question = None
        for question in all_questions:
            if question.id not in answered_questions:
                current_question = question
                break
        
        if not current_question:
            # Assessment complete
            assessment.completed_at = timezone.now()
            assessment.save()
            return redirect('analysis:assessment_complete', session_id=session_id)
        
        # Calculate progress
        total_questions = min(all_questions.count(), 10)  # Max 10 questions
        answered_count = len(answered_questions)
        current_question_number = answered_count + 1
        progress_percentage = (answered_count / total_questions) * 100 if total_questions > 0 else 0
        
        context = {
            'assessment': assessment,
            'session_id': session_id,
            'current_question': current_question,
            'current_question_number': current_question_number,
            'total_questions': total_questions,
            'progress_percentage': progress_percentage,
        }
        
        return render(request, 'analysis/clean_assessment.html', context)
        
    except Exception as e:
        messages.error(request, f"Assessment error: {str(e)}")
        return redirect('user_api:individual_dashboard')


@require_http_methods(["POST"])
@ratelimit(key='user', rate=settings.RATE_LIMIT_SNAPSHOT, block=True)
def capture_snapshot_clean(request, session_id):
    """Handle background snapshot capture for analysis"""
    try:
        data = json.loads(request.body)
        
        assessment = get_object_or_404(
            IndividualAssessment,
            session_id=session_id
        )
        
        # Extract image data
        image_data = data.get('image_data', '').replace('data:image/jpeg;base64,', '')
        analysis_type = data.get('analysis_type', 'unknown')
        question_id = data.get('question_id')
        timestamp = data.get('timestamp')
        
        if not image_data:
            return JsonResponse({'success': False, 'error': 'No image data provided'})
            
        is_valid, error_msg = validate_image_b64(image_data)
        if not is_valid:
            return JsonResponse({'success': False, 'error': error_msg}, status=400)
        
        # Get question
        question = None
        if question_id:
            try:
                question = PlatformQuestion.objects.get(id=question_id)
            except PlatformQuestion.DoesNotExist:
                pass
        
        # Perform analysis based on type
        analysis_result = {}
        if analysis_type == 'body_language' and BODY_LANGUAGE_ANALYSIS_AVAILABLE:
            try:
                analysis_result = analyze_body_language_base64(image_data)
            except Exception as e:
                print(f"Body language analysis failed: {e}")
                analysis_result = {"error": str(e)}
                
        elif analysis_type == 'attire' and ATTIRE_ANALYSIS_AVAILABLE:
            try:
                analysis_result = analyze_attire_base64(image_data)
            except Exception as e:
                print(f"Attire analysis failed: {e}")
                analysis_result = {"error": str(e)}
        
        # BUG FIX: AssessmentSnapshot does not have fields 'question', 'snapshot_data', or
        # 'analysis_result'.  Use the actual model fields: analysis_data (JSONField) and score.
        snapshot_score = None
        if isinstance(analysis_result, dict) and not analysis_result.get('error'):
            for key in ('overall_score', 'score', 'confidence_score', 'posture_score', 'attire_score'):
                val = analysis_result.get(key)
                if val is not None:
                    try:
                        snapshot_score = float(val)
                        if snapshot_score <= 1.0:
                            snapshot_score *= 10
                        break
                    except (ValueError, TypeError):
                        pass
        
        snapshot = AssessmentSnapshot.objects.create(
            assessment=assessment,
            analysis_type=analysis_type,
            timestamp=timezone.now(),
            score=snapshot_score,
            analysis_data={
                'analysis_result': analysis_result,
                'question_id': question_id,
            },
            feedback=', '.join(analysis_result.get('feedback', [])) if isinstance(analysis_result, dict) else ''
        )
        
        return JsonResponse({
            'success': True,
            'snapshot_id': snapshot.id,
            'analysis_result': analysis_result
        })
        
    except Exception as e:
        print(f"Snapshot capture failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["POST"])
@ratelimit(key='user', rate=settings.RATE_LIMIT_SUBMISSION, block=True)
def submit_response_clean(request, session_id):
    """Handle clean response submission with speech analysis"""
    try:
        data = json.loads(request.body)
        
        assessment = get_object_or_404(
            IndividualAssessment,
            session_id=session_id
        )
        
        question_id = data.get('question_id')
        audio_data = data.get('audio_data', '')
        response_time = data.get('response_time', 0)
        fullscreen_violations = data.get('fullscreen_violations', 0)
        
        # Get question
        question = get_object_or_404(PlatformQuestion, id=question_id)
        
        # Save basic response
        response = IndividualAssessmentResponse.objects.create(
            assessment=assessment,
            question=question,
            audio_data=audio_data,
            response_time=response_time,
            fullscreen_violations=fullscreen_violations
        )
        
        # Perform speech analysis in background
        if audio_data:
            is_valid, error_msg = validate_audio_b64(audio_data)
            if not is_valid:
                return JsonResponse({'success': False, 'error': error_msg}, status=400)
                
            if SPEECH_ANALYSIS_AVAILABLE:
                try:
                    # Decode audio data
                    audio_bytes = base64.b64decode(audio_data)
                    
                    # Analyze speech
                    speech_analysis = analyze_speech(audio_bytes, question.question_text)
                    
                    # Update response with analysis
                    response.speech_analysis = speech_analysis
                    response.save()
                    
                except Exception as e:
                    print(f"Speech analysis failed: {e}")
                    response.speech_analysis = {"error": str(e)}
                    response.save()
        
        # Check if assessment is complete
        answered_questions = IndividualAssessmentResponse.objects.filter(
            assessment=assessment
        ).count()
        
        total_questions = PlatformQuestion.objects.filter(
            job_title=assessment.platform_job_title
        ).count()
        
        is_complete = answered_questions >= min(total_questions, 10)  # Max 10 questions
        
        complete_url = None
        if is_complete:
            assessment.completed_at = timezone.now()
            assessment.save()
            complete_url = f'/analysis/assessment/{session_id}/complete/'
        
        return JsonResponse({
            'success': True,
            'response_id': response.id,
            'is_complete': is_complete,
            'complete_url': complete_url
        })
        
    except Exception as e:
        print(f"Response submission failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["POST"])
@ratelimit(key='user', rate=settings.RATE_LIMIT_SNAPSHOT, block=True)
def capture_snapshot_combined(request, session_id):
    """Handle combined assessment snapshot capture with background analysis"""
    try:
        data = json.loads(request.body)
        
        assessment = get_object_or_404(
            IndividualAssessment,
            session_id=session_id
        )
        
        image_data = data.get('image_data', '')
        analysis_type = data.get('analysis_type', 'body_language')
        question_id = data.get('question_id')
        
        # Remove data URL prefix if present
        if image_data.startswith('data:image/'):
            image_data = image_data.split(',', 1)[1]
        
        if not image_data:
            return JsonResponse({'success': False, 'error': 'No image data provided'})
            
        is_valid, error_msg = validate_image_b64(image_data)
        if not is_valid:
            return JsonResponse({'success': False, 'error': error_msg}, status=400)
            
        # Get question if provided
        question = None
        if question_id:
            try:
                question = PlatformQuestion.objects.get(id=question_id)
            except PlatformQuestion.DoesNotExist:
                pass
        
        # Perform analysis based on type
        analysis_result = {}
        if analysis_type == 'body_language' and BODY_LANGUAGE_ANALYSIS_AVAILABLE:
            try:
                analysis_result = analyze_body_language_base64(image_data)
            except Exception as e:
                print(f"Body language analysis failed: {e}")
                analysis_result = {"error": str(e)}
                
        elif analysis_type == 'attire' and ATTIRE_ANALYSIS_AVAILABLE:
            try:
                analysis_result = analyze_attire_base64(image_data)
            except Exception as e:
                print(f"Attire analysis failed: {e}")
                analysis_result = {"error": str(e)}
        
        # Save snapshot with analysis
        # BUG FIX: Extract numeric score from analysis result for proper aggregation on results page.
        # _snapshot_score_from_data() looks at snapshot.score first, then analysis_data['analysis_result'].
        # We must save the analysis_result at the top level of analysis_data so the helper can find it.
        snapshot_score = None
        if isinstance(analysis_result, dict) and not analysis_result.get('error'):
            # Try common score keys from both analyzers
            for key in ('overall_score', 'score', 'confidence_score', 'posture_score', 'attire_score'):
                val = analysis_result.get(key)
                if val is not None:
                    try:
                        snapshot_score = float(val)
                        # Normalize to 0-10 scale if analyzer returns 0-1
                        if snapshot_score <= 1.0:
                            snapshot_score *= 10
                        break
                    except (ValueError, TypeError):
                        pass
        
        # Store analysis_result at the top level so _snapshot_score_from_data() can find it,
        # and keep the question reference and a truncated image preview for debugging.
        snapshot_data = {
            'analysis_result': analysis_result,  # top-level so helper can read it
            'question_id': question_id,
        }
        
        snapshot = AssessmentSnapshot.objects.create(
            assessment=assessment,
            analysis_type=analysis_type,
            timestamp=timezone.now(),
            score=snapshot_score,
            analysis_data=snapshot_data
        )
        
        return JsonResponse({
            'success': True,
            'snapshot_id': snapshot.id,
            'analysis_result': analysis_result
        })
        
    except Exception as e:
        print(f"Combined snapshot capture failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["POST"])
@ratelimit(key='user', rate=settings.RATE_LIMIT_SUBMISSION, block=True)
def submit_response_combined(request, session_id):
    """Handle combined assessment response submission with speech analysis"""
    try:
        data = json.loads(request.body)
        
        assessment = get_object_or_404(
            IndividualAssessment,
            session_id=session_id
        )
        
        question_id = data.get('question_id')
        audio_data = data.get('audio_data', '')
        response_time = data.get('response_time', 0)
        fullscreen_violations = data.get('fullscreen_violations', 0)
        
        # Get question
        question = get_object_or_404(PlatformQuestion, id=question_id)
        
        # Check if response already exists for this question
        existing_response = IndividualAssessmentResponse.objects.filter(
            assessment=assessment,
            question=question
        ).first()
        
        if existing_response:
            return JsonResponse({'success': False, 'error': 'Response already submitted for this question'})
        
        # Save response with initial status
        initial_analysis_data = {
            'fullscreen_violations': fullscreen_violations, 
            'has_audio_data': bool(audio_data)
        }
        
        # Set speech analysis status if we have audio
        if audio_data and SPEECH_ANALYSIS_AVAILABLE:
            initial_analysis_data['speech_analysis_status'] = 'pending'
        else:
            initial_analysis_data['speech_analysis_status'] = 'not_applicable'
        
        response = IndividualAssessmentResponse.objects.create(
            assessment=assessment,
            question=question,
            question_order=IndividualAssessmentResponse.objects.filter(assessment=assessment).count() + 1,
            question_started_at=timezone.now() - timezone.timedelta(seconds=response_time),
            response_started_at=timezone.now() - timezone.timedelta(seconds=response_time//2),
            response_ended_at=timezone.now(),
            response_duration=response_time,
            time_to_start=5,  # Default 5 seconds to start
            analysis_data=initial_analysis_data
        )
        
        # Handle audio data if provided
        if audio_data:
            is_valid, error_msg = validate_audio_b64(audio_data)
            if not is_valid:
                return JsonResponse({'success': False, 'error': error_msg}, status=400)
            try:
                audio_len = len(audio_data)
                est_bytes = int(audio_len * 3 / 4)
                print(f"[Audio] Response Q{IndividualAssessmentResponse.objects.filter(assessment=assessment).count()+1}: "
                      f"base64_len={audio_len} chars, est_decoded={est_bytes} bytes ({est_bytes/1024:.1f} KB)")
                # Store truncated preview only — full data goes to background task
                response.analysis_data['audio_base64_preview'] = audio_data[:60] + '...' if len(audio_data) > 60 else audio_data
                response.analysis_data['audio_b64_length'] = audio_len
                response.analysis_data['audio_est_bytes'] = est_bytes
                response.analysis_data['speech_analysis_status'] = 'pending'
                response.save()
            except Exception as e:
                print(f"Audio storage failed: {e}")
        
        # Start speech analysis in background (don't wait for it)
        if audio_data and SPEECH_ANALYSIS_AVAILABLE:
            _enqueue_speech_analysis(response.id, audio_data, question.question_text)
        
        # Check if assessment is complete
        # BUG FIX: Use assessment.total_questions (the selected subset for THIS session),
        # NOT the total count of all questions in the job title bank, which can be much
        # larger and would cause the assessment to complete prematurely.
        answered_questions = IndividualAssessmentResponse.objects.filter(
            assessment=assessment
        ).count()
        
        total_questions = assessment.total_questions or len(assessment.selected_questions or [])
        if total_questions == 0:
            # Fallback: shouldn't happen but avoid dividing by zero / completing instantly
            total_questions = assessment.platform_job_title.questions.filter(is_active=True).count()
        
        is_complete = answered_questions >= total_questions
        
        if is_complete:
            assessment.status = 'completed'
            assessment.completed_at = timezone.now()
            assessment.save()
        
        return JsonResponse({
            'success': True,
            'response_id': response.id,
            'is_complete': is_complete,
            'answered_questions': answered_questions,
            'total_questions': total_questions
        })
        
    except Exception as e:
        print(f"Combined response submission failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["GET"])
def check_processing_status(request, session_id):
    """Check if any responses are still being processed"""
    try:
        assessment = get_object_or_404(
            IndividualAssessment,
            session_id=session_id
        )
        
        # Check for pending speech analysis
        # BUG FIX: Also escalate timed-out tasks here so the polling page doesn't spin forever.
        all_responses = IndividualAssessmentResponse.objects.filter(assessment=assessment)
        _PROCESSING_TIMEOUT_SECONDS = 600  # 10 minutes
        now = timezone.now()
        
        pending_responses = 0
        failed_responses = 0
        for response in all_responses:
            status = response.analysis_data.get('speech_analysis_status', 'unknown')
            if status == 'pending':
                age = (now - response.created_at).total_seconds()
                if age > _PROCESSING_TIMEOUT_SECONDS:
                    # Escalate to failed so the frontend can unblock
                    response.analysis_data['speech_analysis_status'] = 'failed'
                    response.analysis_data['speech_analysis'] = {
                        'error': f'Processing timed out after {int(age)}s — task may have crashed in qcluster.',
                        'transcription': '',
                        'word_count': 0,
                    }
                    response.save(update_fields=['analysis_data'])
                    print(f"[Timeout] Escalated response {response.id} to 'failed' after {int(age)}s")
                    failed_responses += 1
                else:
                    pending_responses += 1
            elif status == 'failed':
                failed_responses += 1
        
        total_responses = all_responses.count()
        processing_complete = pending_responses == 0
        
        # Log for debugging
        print(f"Processing status: {pending_responses} pending, {failed_responses} failed, out of {total_responses} total")
        
        return JsonResponse({
            'success': True,
            'processing_complete': processing_complete,
            'pending_count': pending_responses,
            'failed_count': failed_responses,
            'total_responses': total_responses,
            'progress_percentage': ((total_responses - pending_responses) / max(total_responses, 1)) * 100
        })
        
    except Exception as e:
        print(f"Processing status check failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def export_role_candidates_csv(request, role_id):
    """Export all candidates for a specific job role as CSV"""
    if not hasattr(request.user, 'business_profile'):
        messages.error(request, "Access denied.")
        return redirect('persona_frontend:home')
        
    job_role = get_object_or_404(JobRole, id=role_id, business_user=request.user.business_profile)
    
    # Query completed assessments for this role
    completed_assessments = Assessment.objects.filter(
        assessment_link__job_role=job_role,
        status='completed'
    ).select_related('result').order_by(F('result__overall_score').desc(nulls_last=True))
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="candidates_{job_role.title}_{datetime.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Candidate Name', 
        'Email', 
        'Overall Score', 
        'Speaking Score', 
        'Body Language Score', 
        'Attire Score', 
        'Completion Date'
    ])
    
    for assessment in completed_assessments:
        result = getattr(assessment, 'result', None)
        writer.writerow([
            assessment.candidate_name or 'Anonymous',
            assessment.candidate_email or 'N/A',
            round(result.overall_score, 1) if result and result.overall_score else 'N/A',
            round(result.confidence_score, 1) if result and result.confidence_score else 'N/A',
            round(result.posture_score, 1) if result and result.posture_score else 'N/A',
            result.get_attire_appropriateness_display() if result and result.attire_appropriateness else 'N/A',
            assessment.completed_at.strftime("%Y-%m-%d %H:%M") if assessment.completed_at else 'N/A'
        ])
        
    return response


@login_required
def achievement_badge(request, session_id):
    """Display achievement badge for a completed assessment"""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user
    )
    
    if assessment.status != 'completed':
        return redirect('analysis:individual_assessment_question', session_id=session_id)
    
    from .badge_utils import get_latest_badge_data
    badge_data = get_latest_badge_data(request.user)
    
    context = {
        'assessment': assessment,
        'badge_data': badge_data,
        'has_achievement': badge_data is not None,
    }
    
    return render(request, 'analysis/achievement_badge.html', context)


@login_required
def download_achievement_badge(request, session_id):
    """Generate and download achievement badge as image"""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user
    )
    
    if assessment.status != 'completed':
        return redirect('analysis:individual_assessment_question', session_id=session_id)
    
    from .badge_utils import get_latest_badge_data
    badge_data = get_latest_badge_data(request.user)
    
    if not badge_data:
        messages.error(request, "No achievements unlocked yet.")
        return redirect('analysis:individual_assessment_complete', session_id=session_id)
    
    # Generate badge as HTML then convert to image
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    import io
    
    html_string = render_to_string('analysis/badge_image.html', {
        'badge_data': badge_data,
        'assessment': assessment,
    })
    
    # Create PDF
    result = io.BytesIO()
    pdf = pisa.pisaDocument(io.BytesIO(html_string.encode('utf-8')), result)
    
    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="persona_achievement_{session_id}.pdf"'
        return response
    
    messages.error(request, "Error generating badge.")
    return redirect('analysis:individual_assessment_complete', session_id=session_id)
