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
import logging

logger = logging.getLogger(__name__)

def _calculate_panel_results(assessment):
    """Calculate per-persona scores and aggregated verdict for a panel session"""
    from .models import PanelSession, PanelPersonaScore, IndividualAssessmentResponse
    
    try:
        panel_session = assessment.panel_session
    except PanelSession.DoesNotExist:
        return None

    responses = assessment.responses.all()
    persona_scores = {}
    
    from .voice_interviewer import PERSONAS
    
    for pid in panel_session.personas:
        persona_responses = responses.filter(interviewer_persona_id=pid)
        if persona_responses.exists():
            scores = []
            for resp in persona_responses:
                eval_data = resp.analysis_data.get('content_evaluation', {})
                score = eval_data.get('content_correctness_score')
                if score is not None:
                    scores.append(score)
            
            if scores:
                avg_score = sum(scores) / len(scores)
                # Store or update per-persona score
                PanelPersonaScore.objects.update_or_create(
                    panel_session=panel_session,
                    persona_id=pid,
                    defaults={
                        'score': avg_score,
                        'feedback': f"Evaluated based on {len(scores)} questions."
                    }
                )
                persona_scores[pid] = avg_score

    # Aggregated score (simple average as per requirements)
    if persona_scores:
        panel_session.aggregated_score = sum(persona_scores.values()) / len(persona_scores)
        
        # Check for synthesis cache
        import hashlib
        # Build data hash from persona scores
        hash_input = f"{assessment.id}_{sorted(persona_scores.items())}"
        data_hash = hashlib.md5(hash_input.encode('utf-8')).hexdigest()
        
        if panel_session.data_hash != data_hash:
            from AnalysisModules.feedback_generator import generate_panel_synthesis_summary
            
            panel_data = {
                'aggregated_score': panel_session.aggregated_score,
                'persona_scores': persona_scores,
                'persona_roster': PERSONAS
            }
            panel_session.ai_synthesis_summary = generate_panel_synthesis_summary(panel_data)
            panel_session.ai_synthesis_cached_at = timezone.now()
            panel_session.data_hash = data_hash
            
        panel_session.save()
    
    return panel_session

def _get_interviewer_persona(assessment, question_index, is_follow_up, user):
    """Helper to get the persona for a question based on interview mode"""
    from .voice_interviewer import PERSONAS
    from UserAPI.models import UserInterviewerPreference
    
    if assessment.interview_mode == 'panel':
        try:
            panel_session = assessment.panel_session
            personas = panel_session.personas
            if not personas:
                return UserInterviewerPreference.objects.get_or_create(user=user)[0].persona_id

            if is_follow_up:
                # Reuse the persona from the last response
                last_response = IndividualAssessmentResponse.objects.filter(
                    assessment=assessment
                ).order_by('-created_at').first()
                if last_response and last_response.interviewer_persona_id:
                    return last_response.interviewer_persona_id
            
            # Rotation: persona index = question_index % num_personas
            return personas[question_index % len(personas)]
        except Exception:
            # Fallback to default persona if panel session is missing
            return UserInterviewerPreference.objects.get_or_create(user=user)[0].persona_id
    else:
        return UserInterviewerPreference.objects.get_or_create(user=user)[0].persona_id

def _sanitize_for_json(obj):
    """Recursively convert numpy scalar types to native Python types for JSON serialization."""
    if hasattr(obj, 'item') and hasattr(obj, 'dtype'):
        return obj.item()
    elif hasattr(obj, 'tolist'):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: _sanitize_for_json(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_for_json(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(_sanitize_for_json(item) for item in obj)
    return obj

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


# Import models
from .models import (
    JobRole, InterviewQuestion, AssessmentLink, Assessment, AssessmentResult,
    PlatformJobTitle, PlatformQuestion, IndividualAssessment, 
    IndividualAssessmentResponse, FollowUpResponse, AssessmentSnapshot,
    BusinessAssessmentResponse, BusinessAssessmentSnapshot, CompanyProfile,
    ResumeReview, CoverLetter, LinkedInPost, PlacementDrive
)
from UserAPI.models import BusinessUser
from AnalysisModules.feedback_generator import (
    evaluate_answer_content,
    generate_feedback_summary,
    generate_improvement_roadmap,
    generate_tailored_questions,
    generate_ai_interview_coach,
    generate_skill_gap_analysis,
    generate_learning_roadmap,
    generate_communication_analysis,
    analyze_answer_and_determine_next_step,
    analyze_star_framework,
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


def _enqueue_speech_analysis(response_id, question_text):
    """Run speech analysis via django-q, falling back to a daemon thread."""
    from .tasks import run_speech_analysis_task

    try:
        from django_q.tasks import async_task
        async_task(run_speech_analysis_task, response_id, question_text)
    except Exception as e:
        print(f"django-q enqueue failed ({e}), using thread fallback")
        import threading
        thread = threading.Thread(
            target=run_speech_analysis_task,
            args=(response_id, question_text),
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
    
    # Get institution members (individual users who joined this business)
    from UserAPI.models import InstitutionMembership
    institution_members = InstitutionMembership.objects.filter(
        business=business_user,
        is_active=True
    ).select_related('individual').order_by('-joined_at')
    
    # Get aggregate stats for institution members
    from AnalysisAPI.models import IndividualAssessment
    member_assessments = IndividualAssessment.objects.filter(
        institution_membership__business=business_user,
        institution_membership__is_active=True,
        status='completed'
    )

    avg_member_score = None
    if member_assessments.exists() and member_assessments.filter(overall_score__isnull=False).exists():
        scores = [a.overall_score for a in member_assessments if a.overall_score]
        if scores:
            avg_member_score = sum(scores) / len(scores)

    # Get recent member assessments with coaching insights
    recent_member_assessments = member_assessments.order_by('-completed_at')[:10]

    context = {
        'job_roles': job_roles,
        'job_roles_with_rankings': job_roles_with_rankings,
        'recent_assessments': recent_assessments,
        'total_roles': job_roles.count(),
        'total_assessments': Assessment.objects.filter(
            assessment_link__job_role__business_user=business_user
        ).count(),
        'institution_code': business_user.institution_code,
        'institution_members': institution_members,
        'total_members': institution_members.count(),
        'total_member_assessments': member_assessments.count(),
        'avg_member_score': avg_member_score,
        'recent_member_assessments': recent_member_assessments,
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
    answered_questions = assessment.responses.values_list('question_text', flat=True)
    total_questions = questions.count()
    current_question_number = len(answered_questions) + 1
    
    # Check if assessment is complete
    if current_question_number > total_questions:
        # Mark as completed and redirect to results
        assessment.status = 'completed'
        assessment.completed_at = timezone.now()
        assessment.save()
        return redirect('analysis:business_assessment_complete', assessment_id=assessment.id)
    
    # Adaptive selection: Pick next question based on current_difficulty
    unasked_questions = questions.exclude(question_text__in=answered_questions)
    
    # Try to find a question matching the current difficulty
    current_question = unasked_questions.filter(difficulty_level=assessment.current_difficulty).first()
    
    if not current_question:
        # Fallback to any remaining question if no match found
        current_question = unasked_questions.first()
    
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
        
        # Adaptive difficulty analysis (always ON for business assessments)
        try:
            transcript = response.analysis_data.get('speech_analysis', {}).get('transcript', '') if isinstance(response.analysis_data, dict) else ''
            adaptive_result = analyze_answer_for_adaptive_difficulty(
                question_text=question.question_text,
                transcript=transcript or question.question_text,  # use question as fallback if no transcript yet
                current_difficulty=assessment.current_difficulty,
            )
            if adaptive_result:
                adaptive_decision = {
                    'question_order': question_order,
                    'previous_difficulty': assessment.current_difficulty,
                    'performance_score': adaptive_result['performance_score'],
                    'next_difficulty': adaptive_result['next_difficulty'],
                    'reason': adaptive_result['reason'],
                }
                if not isinstance(assessment.adaptive_path, list):
                    assessment.adaptive_path = []
                assessment.adaptive_path.append(adaptive_decision)
                assessment.current_difficulty = adaptive_result['next_difficulty']
                assessment.save()
                print(f'[ADAPTIVE-BIZ] Q{question_order}: {adaptive_decision["previous_difficulty"]} → {adaptive_result["next_difficulty"]} (score: {adaptive_result["performance_score"]:.1f})')
            else:
                print(f'[ADAPTIVE-BIZ] Adaptive analysis returned None for Q{question_order}, keeping current difficulty.')
        except Exception as adaptive_err:
            logger.warning('Business adaptive difficulty error: %s', adaptive_err)
        
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
    
    # Get user's 3 most recent assessments for the dashboard history panel
    recent_assessments = IndividualAssessment.objects.filter(
        user=request.user
    ).order_by('-created_at')[:3]
    
    # Get available job titles with per-session question count.
    # session_question_count mirrors select_questions(): all mandatory active
    # questions + 5 randomly-chosen non-mandatory ones = actual questions asked.
    NUM_NON_MANDATORY = 5
    job_titles = PlatformJobTitle.objects.filter(is_active=True).annotate(
        active_question_count=Count('questions', filter=Q(questions__is_active=True)),
        mandatory_question_count=Count(
            'questions',
            filter=Q(questions__is_active=True, questions__is_mandatory=True)
        ),
    ).order_by('title')
    # Attach session_question_count as a plain attribute after annotation so
    # the template can use it directly without a custom template tag.
    for jt in job_titles:
        non_mandatory_pool = jt.active_question_count - jt.mandatory_question_count
        jt.session_question_count = jt.mandatory_question_count + min(non_mandatory_pool, NUM_NON_MANDATORY)
    
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
            return redirect('analysis:individual_assessment_mode_select', session_id=assessment.session_id)
            
        except PlatformJobTitle.DoesNotExist:
            messages.error(request, "Invalid job title selected.")
            return redirect('analysis:individual_dashboard')
    
    return redirect('analysis:individual_dashboard')


@login_required
def individual_assessment_mode_select(request, session_id):
    """Mode selection page for individual assessment"""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user,
        status='pending'
    )

    context = {
        'assessment': assessment,
        'job_title': assessment.platform_job_title,
    }
    return render(request, 'analysis/individual_assessment_mode_select.html', context)


@login_required
@require_http_methods(["POST"])
def individual_assessment_mode_submit(request, session_id):
    """Handle mode selection submission"""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user,
        status='pending'
    )

    interview_mode = request.POST.get('interview_mode')
    if interview_mode not in ['hr', 'technical', 'managerial', 'stress', 'rapid_fire', 'panel']:
        messages.error(request, "Invalid interview mode selected.")
        return redirect('analysis:individual_assessment_mode_select', session_id=session_id)

    # Save the selected mode
    assessment.interview_mode = interview_mode
    assessment.save(update_fields=['interview_mode'])

    if interview_mode == 'panel':
        return redirect('analysis:panel_selection', session_id=session_id)

    return redirect('analysis:individual_assessment_company_select', session_id=session_id)

@login_required
def panel_selection(request, session_id):
    """Selection page for panel interviewers"""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user,
        status='pending'
    )
    
    if assessment.interview_mode != 'panel':
        return redirect('analysis:individual_assessment_mode_select', session_id=session_id)

    from .voice_interviewer import PERSONAS
    
    context = {
        'assessment': assessment,
        'job_title': assessment.platform_job_title,
        'personas': PERSONAS,
    }
    return render(request, 'analysis/panel_selection.html', context)

@login_required
@require_http_methods(["POST"])
def panel_submit(request, session_id):
    """Handle panel selection submission"""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user,
        status='pending'
    )

    selected_personas = request.POST.getlist('personas')
    
    if len(selected_personas) < 2 or len(selected_personas) > 3:
        messages.error(request, "Please select 2 or 3 personas for the panel.")
        return redirect('analysis:panel_selection', session_id=session_id)

    from .voice_interviewer import PERSONAS
    for pid in selected_personas:
        if pid not in PERSONAS:
            messages.error(request, f"Invalid persona selected: {pid}")
            return redirect('analysis:panel_selection', session_id=session_id)

    # Create PanelSession
    from .models import PanelSession
    PanelSession.objects.update_or_create(
        assessment=assessment,
        defaults={'personas': selected_personas}
    )

    return redirect('analysis:individual_assessment_company_select', session_id=session_id)

@login_required
def individual_assessment_company_select(request, session_id):
    """Company selection page for individual assessment"""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user,
        status='pending'
    )
    
    companies = CompanyProfile.objects.all()

    context = {
        'assessment': assessment,
        'job_title': assessment.platform_job_title,
        'companies': companies,
    }
    return render(request, 'analysis/individual_assessment_company_select.html', context)


@login_required
@require_http_methods(["POST"])
def individual_assessment_company_submit(request, session_id):
    """Handle company selection submission"""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user,
        status='pending'
    )

    company_id = request.POST.get('company_id')
    
    if company_id:
        try:
            company = CompanyProfile.objects.get(id=company_id)
            assessment.target_company = company
        except CompanyProfile.DoesNotExist:
            messages.error(request, "Invalid company selected.")
            return redirect('analysis:individual_assessment_company_select', session_id=session_id)
    else:
        # User opted to skip (no company selected)
        assessment.target_company = None

    assessment.save(update_fields=['target_company'])

    return redirect('analysis:individual_assessment_setup', session_id=session_id)



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
def video_consent_view(request, session_id):
    """Video recording consent screen for first-time users"""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user,
        status='pending'
    )
    
    if request.method == 'POST':
        consent_given = request.POST.get('consent_given') == 'on'
        
        if consent_given:
            # Record consent timestamp
            profile = request.user.individual_profile
            profile.video_consent_given_at = timezone.now()
            profile.save()
            
            messages.success(request, 'Consent recorded. Starting your interview.')
            return redirect('analysis:start_individual_assessment_session', session_id=session_id)
        else:
            messages.info(request, 'Consent declined. You can change your mind later.')
            return redirect('analysis:individual_dashboard')
    
    context = {
        'user': request.user,
        'session_id': session_id,
    }
    return render(request, 'analysis/video_consent.html', context)


@login_required
def start_individual_assessment_session(request, session_id):
    """Start the actual assessment session, optionally processing an uploaded resume."""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user,
        status='pending'
    )
    
    # Check if user has given video consent
    if not request.user.individual_profile.video_consent_given_at:
        return redirect('analysis:video_consent', session_id=session_id)

    resume_text = None
    if request.method == 'POST':
        # Handle adaptive mode and practice mode toggles
        adaptive_mode = request.POST.get('adaptive_mode', 'true') == 'true'
        practice_mode = request.POST.get('practice_mode', 'false') == 'true'
        assessment.adaptive_mode = adaptive_mode
        assessment.is_practice_mode = practice_mode
        assessment.save()

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
                interview_mode=assessment.interview_mode,
                company_notes=assessment.target_company.interview_style_notes if assessment.target_company else None
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


from AnalysisModules.feedback_generator import generate_question_hint
import json

@require_http_methods(["POST"])
@login_required
def get_question_hint(request, session_id):
    """API endpoint to get a hint for a question in practice mode."""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user,
        status='in_progress'
    )

    if not assessment.is_practice_mode:
        return JsonResponse({'error': 'Hints are only available in Practice Mode.'}, status=403)

    try:
        data = json.loads(request.body)
        question_order = str(data.get('question_order', '1'))
        question_text = data.get('question_text', '')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data.'}, status=400)
        
    if not question_text:
        return JsonResponse({'error': 'Question text is required.'}, status=400)

    hints_used = assessment.hints_used_per_question.get(question_order, 0)
    
    if hints_used >= 1:
        return JsonResponse({'error': 'Hint limit reached for this question.'}, status=429)

    company_notes = assessment.target_company.interview_style_notes if assessment.target_company else None
    
    # Generate hint
    hint_text = generate_question_hint(
        question_text=question_text, 
        interview_mode=assessment.interview_mode,
        company_notes=company_notes
    )
    
    # Increment hint count
    assessment.hints_used_per_question[question_order] = hints_used + 1
    assessment.save(update_fields=['hints_used_per_question'])
    
    return JsonResponse({'hint': hint_text})


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
    
    # Check for active follow-up
    is_follow_up = bool(assessment.pending_follow_up_text)
    
    if is_follow_up:
        # Create a dummy question-like object for the template
        class FollowUpQuestion:
            question_text = assessment.pending_follow_up_text
            question_type = "follow_up"
            difficulty_level = assessment.current_difficulty
        current_question = FollowUpQuestion()
    else:
        # Get current planned question
        current_question = assessment.get_next_question()
        
        if not current_question:
            # No more questions, complete the assessment
            return redirect('analysis:complete_individual_assessment', session_id=session_id)
            
    from .voice_interviewer import generate_question_audio, get_persona_avatar, PERSONAS
    persona_id = _get_interviewer_persona(assessment, assessment.current_question_index, is_follow_up, request.user)
    audio_url = generate_question_audio(current_question.question_text, persona_id, session_id) if current_question else None
    persona_avatar = get_persona_avatar(persona_id)
    persona_name = PERSONAS.get(persona_id, {}).get('name', 'Interviewer')
    
    # Add time limit for Rapid Fire mode
    time_limit_seconds = 12 if assessment.interview_mode == 'rapid_fire' else None
    
    context = {
        'audio_url': audio_url,
        'assessment': assessment,
        'question': current_question,
        'is_follow_up': is_follow_up,
        'question_number': f"{assessment.current_question_index} (Follow-up)" if is_follow_up else assessment.current_question_index + 1,
        'total_questions': assessment.total_questions,
        'progress_percentage': ((assessment.current_question_index + 1) / assessment.total_questions) * 100,
        'session_id': session_id,
        'adaptive_mode': assessment.adaptive_mode,
        'current_difficulty': assessment.current_difficulty,
        'time_limit_seconds': time_limit_seconds,
        'persona_avatar': persona_avatar,
        'persona_name': persona_name,
        'persona_id': persona_id,
        'analysis_status': {
            'attire_available': ATTIRE_ANALYSIS_AVAILABLE,
            'body_language_available': BODY_LANGUAGE_ANALYSIS_AVAILABLE,
            'speech_available': SPEECH_ANALYSIS_AVAILABLE,
        }
    }
    return render(request, 'analysis/individual_assessment_question.html', context)


@require_http_methods(["POST"])
@ratelimit(key='user', rate=settings.RATE_LIMIT_SUBMISSION, block=True)
@login_required
def submit_assessment_response(request, session_id):
    """Submit response for current question and move to next"""
    try:
        assessment = get_object_or_404(
            IndividualAssessment,
            session_id=session_id,
            user=request.user,
            status='in_progress'
        )
        logger.info(f"[DIAG] submit_assessment_response START: session_id={session_id}, current_question_index={assessment.current_question_index}")
        
        # Check if we are answering a pending follow-up
        is_answering_follow_up = bool(assessment.pending_follow_up_text)

        if is_answering_follow_up:
            current_question = None
            question_text_for_analysis = assessment.pending_follow_up_text
            # Find the parent response (the last submitted response)
            parent_response = IndividualAssessmentResponse.objects.filter(
                assessment=assessment
            ).order_by('-created_at').first()
        else:
            # Get current planned question
            current_question = assessment.get_next_question()
            if not current_question:
                # No more questions — this is a duplicate call after the assessment already
                # advanced past the last question.  Return gracefully instead of crashing.
                is_complete = assessment.current_question_index >= assessment.total_questions
                logger.warning(
                    'submit_assessment_response: no current question for session %s '
                    '(index=%d total=%d) — probable duplicate POST, returning current state.',
                    session_id, assessment.current_question_index, assessment.total_questions,
                )
                response_data = {
                    'success': True,
                    'is_complete': is_complete,
                    'next_question_url': f'/analysis/individual/{session_id}/question/' if not is_complete else None,
                    'complete_url': f'/analysis/individual/{session_id}/processing/' if is_complete else None,
                }
                if not is_complete:
                    is_follow_up = bool(assessment.pending_follow_up_text)
                    if is_follow_up:
                        next_q_text = assessment.pending_follow_up_text
                        next_q_type_display = "Follow-up"
                        next_q_is_mandatory = False
                    else:
                        next_q = assessment.get_next_question()
                        next_q_text = next_q.question_text if next_q else ""
                        next_q_type_display = next_q.get_question_type_display() if next_q else ""
                        next_q_is_mandatory = next_q.is_mandatory if next_q else False
                        
                    from UserAPI.models import UserInterviewerPreference
                    from .voice_interviewer import generate_question_audio, get_persona_avatar, PERSONAS
                    persona_id = UserInterviewerPreference.objects.get_or_create(user=request.user)[0].persona_id
                    audio_url = generate_question_audio(next_q_text, persona_id, session_id) if next_q_text else None
                        
                    response_data['next_question'] = {
                        'is_follow_up': is_follow_up,
                        'question_text': next_q_text,
                        'question_type_display': next_q_type_display,
                        'is_mandatory': next_q_is_mandatory,
                        'difficulty_level': assessment.current_difficulty,
                        'question_number': f"{assessment.current_question_index} (Follow-up)" if is_follow_up else assessment.current_question_index + 1,
                        'progress_percentage': ((assessment.current_question_index + 1) / assessment.total_questions) * 100,
                        'audio_url': audio_url,
                        'persona_avatar': get_persona_avatar(persona_id),
                        'persona_name': PERSONAS.get(persona_id, {}).get('name', 'Interviewer'),
                        'persona_id': persona_id,
                        'time_limit_seconds': 12 if assessment.interview_mode == 'rapid_fire' else None,
                    }
                return JsonResponse(response_data)
            question_text_for_analysis = current_question.question_text
            parent_response = None

        # Idempotency guard: if a response for this exact question_order already exists
        # (i.e. the first POST already committed before this duplicate arrived), return
        # the current state instead of creating a duplicate record and crashing.
        if not is_answering_follow_up:
            already_answered = IndividualAssessmentResponse.objects.filter(
                assessment=assessment,
                question=current_question,
                question_order=assessment.current_question_index + 1,
            ).exists()
            logger.info(f"[DIAG] Idempotency check: already_answered={already_answered}, question_order={assessment.current_question_index + 1}")
            if already_answered:
                is_complete = assessment.current_question_index >= assessment.total_questions
                logger.warning(
                    'submit_assessment_response: duplicate POST detected for session %s '
                    'question_order=%d — returning current state without re-processing.',
                    session_id, assessment.current_question_index + 1,
                )
                logger.info(f"[DIAG] Idempotency guard fired! Returning state for question_index={assessment.current_question_index}")
                response_data = {
                    'success': True,
                    'is_complete': is_complete,
                    'next_question_url': f'/analysis/individual/{session_id}/question/' if not is_complete else None,
                    'complete_url': f'/analysis/individual/{session_id}/processing/' if is_complete else None,
                }
                if not is_complete:
                    is_follow_up = bool(assessment.pending_follow_up_text)
                    if is_follow_up:
                        next_q_text = assessment.pending_follow_up_text
                        next_q_type_display = "Follow-up"
                        next_q_is_mandatory = False
                    else:
                        next_q = assessment.get_next_question()
                        next_q_text = next_q.question_text if next_q else ""
                        next_q_type_display = next_q.get_question_type_display() if next_q else ""
                        next_q_is_mandatory = next_q.is_mandatory if next_q else False
                        
                    response_data['next_question'] = {
                        'is_follow_up': is_follow_up,
                        'question_text': next_q_text,
                        'question_type_display': next_q_type_display,
                        'is_mandatory': next_q_is_mandatory,
                        'difficulty_level': assessment.current_difficulty,
                        'question_number': f"{assessment.current_question_index} (Follow-up)" if is_follow_up else assessment.current_question_index + 1,
                        'progress_percentage': ((assessment.current_question_index + 1) / assessment.total_questions) * 100,
                        'time_limit_seconds': 12 if assessment.interview_mode == 'rapid_fire' else None,
                    }
                return JsonResponse(response_data)
        
        # Parse request data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        # Handle skip
        if data.get('skipped'):
            if not is_answering_follow_up:
                persona_id = _get_interviewer_persona(assessment, assessment.current_question_index, False, request.user)
                IndividualAssessmentResponse.objects.create(
                    assessment=assessment,
                    question=current_question,
                    question_order=assessment.current_question_index + 1,
                    question_started_at=timezone.now(),
                    response_started_at=timezone.now(),
                    response_ended_at=timezone.now(),
                    response_duration=0,
                    time_to_start=0,
                    interviewer_persona_id=persona_id,
                    analysis_data={
                        'skipped': True,
                        'skip_reason': data.get('skip_reason', 'user_skipped'),
                        'fullscreen_violations': data.get('fullscreen_violations', 0),
                    }
                )
                assessment.current_question_index += 1
            else:
                # If they skipped a follow-up, just clear it and move to next planned question
                assessment.pending_follow_up_text = None
                assessment.pending_follow_up_reason = None
                assessment.current_question_index += 1
                
            assessment.save()
            is_complete = assessment.current_question_index >= assessment.total_questions
            response_data = {
                'success': True,
                'is_complete': is_complete,
                'next_question_url': f'/analysis/individual/{session_id}/question/' if not is_complete else None,
                'complete_url': f'/analysis/individual/{session_id}/processing/' if is_complete else None,
            }
            if not is_complete:
                is_follow_up = bool(assessment.pending_follow_up_text)
                if is_follow_up:
                    next_q_text = assessment.pending_follow_up_text
                    next_q_type_display = "Follow-up"
                    next_q_is_mandatory = False
                else:
                    next_q = assessment.get_next_question()
                    next_q_text = next_q.question_text if next_q else ""
                    next_q_type_display = next_q.get_question_type_display() if next_q else ""
                    next_q_is_mandatory = next_q.is_mandatory if next_q else False
                    
                from .voice_interviewer import generate_question_audio, get_persona_avatar, PERSONAS
                next_persona_id = _get_interviewer_persona(assessment, assessment.current_question_index, is_follow_up, request.user)
                audio_url = generate_question_audio(next_q_text, next_persona_id, session_id) if next_q_text else None
                    
                response_data['next_question'] = {
                    'is_follow_up': is_follow_up,
                    'question_text': next_q_text,
                    'question_type_display': next_q_type_display,
                    'is_mandatory': next_q_is_mandatory,
                    'difficulty_level': assessment.current_difficulty,
                    'question_number': f"{assessment.current_question_index} (Follow-up)" if is_follow_up else assessment.current_question_index + 1,
                    'progress_percentage': ((assessment.current_question_index + 1) / assessment.total_questions) * 100,
                    'audio_url': audio_url,
                    'persona_avatar': get_persona_avatar(next_persona_id),
                    'persona_name': PERSONAS.get(next_persona_id, {}).get('name', 'Interviewer'),
                    'persona_id': next_persona_id,
                    'time_limit_seconds': 12 if assessment.interview_mode == 'rapid_fire' else None,
                }
            return JsonResponse(response_data)

        # Create response record
        if is_answering_follow_up:
            if not parent_response:
                return JsonResponse({'error': 'No parent response found for follow-up'}, status=400)

            follow_up_response = FollowUpResponse.objects.create(
                parent_response=parent_response,
                follow_up_prompt=question_text_for_analysis,
                follow_up_reason=assessment.pending_follow_up_reason,
                answer_text=data.get('response_text', ''),
            )
            response = None
        else:
            persona_id = _get_interviewer_persona(assessment, assessment.current_question_index, False, request.user)
            response = IndividualAssessmentResponse.objects.create(
                assessment=assessment,
                question=current_question,
                question_order=assessment.current_question_index + 1,
                question_started_at=timezone.now(),
                response_started_at=timezone.now(),
                response_ended_at=timezone.now(),
                # FormData sends all values as strings (e.g. "10.482"); parse through
                # float() first so fractional-second values don't crash the PositiveIntegerField.
                response_duration=int(float(data.get('response_duration', 0) or 0)),
                time_to_start=int(float(data.get('time_to_start', 0) or 0)),
                interviewer_persona_id=persona_id
            )
        
        # Process video/audio if provided
        video_file = request.FILES.get('video_file')
        if video_file or ('audio_data' in data and data['audio_data']):
            if not video_file:
                is_valid, error_msg = validate_audio_b64(data['audio_data'])
                if not is_valid:
                    return JsonResponse({'error': error_msg}, status=400)
            
            try:
                if video_file:
                    filename = f"response_{assessment.id}_{assessment.current_question_index + 1}_{uuid.uuid4().hex[:8]}.webm"
                    if is_answering_follow_up:
                        follow_up_response.video_file.save(filename, video_file)
                    else:
                        response.video_file.save(filename, video_file)

                    # ----------------------------------------------------------------
                    # Audio extraction from the saved video.
                    #
                    # IMPORTANT: FieldFile.save() above fully reads the upload stream,
                    # leaving the file pointer at EOF.  We must seek(0) before calling
                    # video_file.chunks() so the temp file receives the actual content
                    # instead of 0 bytes — which was the root cause of empty audio_bytes
                    # and silent speech-analysis failures.
                    # ----------------------------------------------------------------
                    import tempfile
                    import os
                    import subprocess
                    from django.core.files.base import ContentFile

                    video_file.seek(0)  # reset stream after FieldFile.save() consumed it
                    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as temp_video:
                        for chunk in video_file.chunks():
                            temp_video.write(chunk)
                        temp_video_path = temp_video.name

                    # ----------------------------------------------------------------
                    # Extract audio via raw ffmpeg instead of moviepy's VideoFileClip.
                    #
                    # Chrome's MediaRecorder writes .webm files as a live stream —
                    # the header has no duration/seek metadata.  MoviePy's VideoFileClip
                    # asks ffmpeg for that duration upfront and raises:
                    #   OSError: MoviePy error: failed to read the duration of …
                    # Raw ffmpeg (invoked directly) handles this fine because it just
                    # reads packets without needing the header duration field.
                    #
                    # imageio_ffmpeg is a moviepy dependency that ships a bundled ffmpeg
                    # binary, so we use it to locate the binary reliably instead of
                    # relying on ffmpeg being on PATH.
                    # ----------------------------------------------------------------
                    try:
                        from imageio_ffmpeg import get_ffmpeg_exe
                        ffmpeg_bin = get_ffmpeg_exe()
                    except Exception:
                        ffmpeg_bin = "ffmpeg"  # fall back to PATH

                    temp_audio_path = None
                    audio_bytes = b''

                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                        temp_audio_path = temp_audio.name

                    try:
                        ffmpeg_result = subprocess.run(
                            [
                                ffmpeg_bin,
                                "-y",               # overwrite output without prompting
                                "-i", temp_video_path,
                                "-vn",              # strip video stream
                                "-acodec", "pcm_s16le",
                                "-ar", "16000",     # Whisper expects 16kHz
                                "-ac", "1",         # Whisper expects mono
                                temp_audio_path,
                            ],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                    except FileNotFoundError:
                        ffmpeg_result = None
                        logger.warning(
                            "[DIAG] submit_assessment_response: ffmpeg binary not found — "
                            "audio extraction skipped for session %s",
                            session_id,
                        )

                    if ffmpeg_result is not None and ffmpeg_result.returncode == 0 \
                            and os.path.exists(temp_audio_path) \
                            and os.path.getsize(temp_audio_path) > 0:
                        with open(temp_audio_path, 'rb') as f:
                            audio_bytes = f.read()

                        # Persist extracted audio to audio_file so it is stored
                        # independently of the video (enables offline re-analysis).
                        audio_filename = (
                            f"response_{assessment.id}_"
                            f"{assessment.current_question_index + 1}_"
                            f"{uuid.uuid4().hex[:8]}.wav"
                        )
                        if is_answering_follow_up:
                            follow_up_response.audio_file.save(
                                audio_filename, ContentFile(audio_bytes), save=False
                            )
                        else:
                            response.audio_file.save(
                                audio_filename, ContentFile(audio_bytes), save=False
                            )
                    else:
                        if ffmpeg_result is not None and ffmpeg_result.returncode != 0:
                            stderr_text = ffmpeg_result.stderr.decode(errors="replace")
                            logger.warning(
                                "[DIAG] submit_assessment_response: ffmpeg exited %d for session %s — "
                                "video may have no audio track.\n%s",
                                ffmpeg_result.returncode, session_id, stderr_text,
                            )
                        else:
                            logger.warning(
                                "[DIAG] submit_assessment_response: ffmpeg produced no audio output "
                                "for session %s — video may have no audio track.",
                                session_id,
                            )

                    os.remove(temp_video_path)
                    if temp_audio_path and os.path.exists(temp_audio_path):
                        os.remove(temp_audio_path)

                else:
                    audio_bytes = base64.b64decode(data['audio_data'].split(',')[1])

                # Analyze speech if available
                if SPEECH_ANALYSIS_AVAILABLE and audio_bytes:
                    speech_analysis = analyze_speech(
                        audio_bytes,
                        question_text_for_analysis,
                        int(float(data.get('response_duration', 0) or 0))
                    )

                    if is_answering_follow_up:
                        follow_up_response.answer_text = speech_analysis.get('transcription', '') or data.get('response_text', '')
                        follow_up_response.save()
                    else:
                        response.response_text = speech_analysis.get('transcription', '')
                        response.fluency_score = speech_analysis.get('fluency_score', 0)
                        response.pronunciation_score = speech_analysis.get('pronunciation_score', 0)
                        response.relevance_score = speech_analysis.get('content_score', 0)
                        response.confidence_score = speech_analysis.get('confidence_score', 0)

                        ideal_pts = current_question.ideal_answer_points if current_question else None
                        raw_analysis_data = {
                            'speech_analysis': speech_analysis,
                            'content_evaluation': evaluate_answer_content(
                                question_text=question_text_for_analysis,
                                transcript=speech_analysis.get('transcription', ''),
                                ideal_answer_points=ideal_pts,
                            ),
                        }
                        response.analysis_data = _sanitize_for_json(raw_analysis_data)

                        response.fluency_score = _sanitize_for_json(response.fluency_score)
                        response.pronunciation_score = _sanitize_for_json(response.pronunciation_score)
                        response.relevance_score = _sanitize_for_json(response.relevance_score)
                        response.confidence_score = _sanitize_for_json(response.confidence_score)

            except Exception as e:
                logger.exception("[DIAG] submit_assessment_response: Audio processing error — full traceback:")
                print(f"Audio processing error: {e}")
        
        if not is_answering_follow_up:
            response.save()
        elif not follow_up_response.answer_text:
            follow_up_response.answer_text = data.get('response_text', '')
            follow_up_response.save()
        
        # Adaptive difficulty adjustment (if enabled and not the last question)
        if not is_answering_follow_up and assessment.adaptive_mode and assessment.current_question_index + 1 < assessment.total_questions:
            try:
                # Get performance metrics for adaptive analysis
                content_score = None
                voice_score = None
                body_score = None
                
                if response.analysis_data and 'content_evaluation' in response.analysis_data:
                    content_score = response.analysis_data['content_evaluation'].get('content_correctness_score')
                
                if response.confidence_score is not None:
                    voice_score = response.confidence_score
                
                # Get body language score from recent snapshots
                recent_snapshots = assessment.snapshots.filter(
                    analysis_type='body_language'
                ).order_by('-timestamp')[:3]
                if recent_snapshots.exists():
                    body_scores = [_snapshot_score_from_data(s) for s in recent_snapshots if _snapshot_score_from_data(s)]
                    if body_scores:
                        body_score = sum(body_scores) / len(body_scores)
                
                # Determine if this is a behavioral question for STAR analysis
                _is_behavioral = (
                    current_question is not None
                    and current_question.question_type == 'behavioral'
                )

                # Call adaptive analysis (combined with STAR for behavioral questions)
                adaptive_result = analyze_answer_and_determine_next_step(
                    question_text=question_text_for_analysis,
                    transcript=response.response_text or '',
                    current_difficulty=assessment.current_difficulty,
                    session_follow_up_count=assessment.session_follow_up_count,
                    content_score=content_score,
                    voice_confidence_score=voice_score,
                    body_language_score=body_score,
                    is_behavioral=_is_behavioral,
                    max_follow_ups=2,
                    interview_mode=assessment.interview_mode,
                    company_notes=assessment.target_company.interview_style_notes if assessment.target_company else None
                )
                
                if adaptive_result:
                    # Save STAR analysis for behavioral questions (independent of adaptive path)
                    _star = adaptive_result.get('star_analysis')
                    if _star is not None:
                        try:
                            response.star_analysis = _star
                            response.save(update_fields=['star_analysis'])
                            print(f'[STAR] Saved STAR analysis for Q{assessment.current_question_index + 1}: score={_star.get("score")}')
                        except Exception as _star_save_err:
                            logger.warning('[STAR] Failed to save star_analysis for response %s: %s', response.id, _star_save_err)

                    # Check if a follow-up was generated
                    if adaptive_result.get('generate_follow_up') and assessment.session_follow_up_count < 2:
                        assessment.pending_follow_up_text = adaptive_result.get('follow_up_question')
                        assessment.pending_follow_up_reason = adaptive_result.get('follow_up_reason')
                        # Do NOT increment current_question_index so we stay on the same timeline spot
                        print(f'[FOLLOW-UP] Generated follow up for Q{assessment.current_question_index + 1}')
                    else:
                        # Record adaptive decision
                        adaptive_decision = {
                            'question_order': assessment.current_question_index + 1,
                            'previous_difficulty': assessment.current_difficulty,
                            'performance_score': adaptive_result['performance_score'],
                            'next_difficulty': adaptive_result['next_difficulty'],
                            'reason': adaptive_result['reason']
                        }
                        assessment.adaptive_path.append(adaptive_decision)
                        
                        # Update current difficulty
                        assessment.current_difficulty = adaptive_result['next_difficulty']
                        
                        # Swap out upcoming unasked non-mandatory questions
                        assessment.adjust_upcoming_questions_for_difficulty()
                        
                        # Log the adaptive decision
                        print(f'[ADAPTIVE] Q{assessment.current_question_index + 1}: {assessment.current_difficulty} → {adaptive_result["next_difficulty"]} (score: {adaptive_result["performance_score"]:.1f})')
                        
                        # Clear any pending follow-ups just in case
                        assessment.pending_follow_up_text = None
                        assessment.pending_follow_up_reason = None
                        
                        # Move to next question if we're not asking a follow-up
                        assessment.current_question_index += 1
                else:
                    # Fallback: log but don't change difficulty
                    print(f'[ADAPTIVE] Analysis failed for Q{assessment.current_question_index + 1}, keeping current difficulty')
                    logger.warning('Adaptive difficulty analysis failed, falling back to current difficulty')
                    assessment.current_question_index += 1
                    
            except Exception as e:
                # Fallback: log error but continue with current difficulty
                logger.exception("[DIAG] submit_assessment_response: Error in adaptive analysis block — full traceback:")  # DIAG
                print(f'[ADAPTIVE] Error in adaptive analysis: {e}')
                logger.warning(f'Adaptive difficulty analysis error: {e}')
                assessment.current_question_index += 1
        else:
            # Not adaptive mode or last question, or a follow-up answer, just advance index
            if is_answering_follow_up:
                assessment.session_follow_up_count += 1
                assessment.pending_follow_up_text = None
                assessment.pending_follow_up_reason = None
            assessment.current_question_index += 1

            # STAR analysis for behavioral questions not covered by the adaptive call above.
            # This path fires when: adaptive mode is OFF, OR this is the final question
            # (adaptive block condition requires index+1 < total_questions).
            # We only call Groq here; never for non-behavioral or skipped responses.
            if (
                not is_answering_follow_up
                and current_question is not None
                and current_question.question_type == 'behavioral'
                and (response.response_text or '').strip()
            ):
                try:
                    _star = analyze_star_framework(
                        question_text=current_question.question_text,
                        transcript=response.response_text,
                    )
                    if _star is not None:
                        response.star_analysis = _star
                        response.save(update_fields=['star_analysis'])
                        print(f'[STAR] Saved STAR analysis (standalone) for Q{assessment.current_question_index}: score={_star.get("score")}')
                    else:
                        logger.warning('[STAR] analyze_star_framework returned None for response %s', response.id)
                except Exception as _star_err:
                    logger.warning('[STAR] Standalone STAR analysis failed for response %s: %s', response.id, _star_err)
        
        assessment.save()
        
        # Check if assessment is complete — send candidate to processing interstitial first
        is_complete = assessment.current_question_index >= assessment.total_questions
        logger.info(f"[DIAG] Assessment save complete. is_complete={is_complete}, new current_question_index={assessment.current_question_index}, pending_follow_up={bool(assessment.pending_follow_up_text)}")
        
        response_data = {
            'success': True,
            'is_complete': is_complete,
            'next_question_url': f'/analysis/individual/{session_id}/question/' if not is_complete else None,
            'complete_url': f'/analysis/individual/{session_id}/processing/' if is_complete else None
        }
        if not is_complete:
            is_follow_up = bool(assessment.pending_follow_up_text)
            if is_follow_up:
                next_q_text = assessment.pending_follow_up_text
                next_q_type_display = "Follow-up"
                next_q_is_mandatory = False
            else:
                next_q = assessment.get_next_question()
                next_q_text = next_q.question_text if next_q else ""
                next_q_type_display = next_q.get_question_type_display() if next_q else ""
                next_q_is_mandatory = next_q.is_mandatory if next_q else False
                
                from UserAPI.models import UserInterviewerPreference
                from .voice_interviewer import generate_question_audio, get_persona_avatar, PERSONAS
                persona_id = UserInterviewerPreference.objects.get_or_create(user=request.user)[0].persona_id
                audio_url = generate_question_audio(next_q_text, persona_id, session_id) if next_q_text else None
                
            response_data['next_question'] = {
                'is_follow_up': is_follow_up,
                'question_text': next_q_text,
                'question_type_display': next_q_type_display,
                'is_mandatory': next_q_is_mandatory,
                'difficulty_level': assessment.current_difficulty,
                'question_number': f"{assessment.current_question_index} (Follow-up)" if is_follow_up else assessment.current_question_index + 1,
                'progress_percentage': ((assessment.current_question_index + 1) / assessment.total_questions) * 100,
                'audio_url': audio_url,
                'persona_avatar': get_persona_avatar(persona_id),
                'persona_name': PERSONAS.get(persona_id, {}).get('name', 'Interviewer'),
                'persona_id': persona_id,
            }
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.exception("[DIAG] submit_assessment_response: Outer exception — full traceback:")  # DIAG
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
@ratelimit(key='user', rate=settings.RATE_LIMIT_SNAPSHOT, block=True)
@login_required
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

    # Generate AI Interview Coach insights (only if not already generated)
    if assessment.ai_coach_status == 'pending' or assessment.ai_coach_status == 'failed':
        try:
            # Build interview transcript from responses
            transcript_parts = []
            questions_list = []
            for response in responses:
                questions_list.append(response.question.question_text)
                speech_analysis = response.analysis_data.get('speech_analysis', {}) if isinstance(response.analysis_data, dict) else {}
                transcript = speech_analysis.get('transcript', '') if isinstance(speech_analysis, dict) else ''
                if transcript:
                    transcript_parts.append(f"Q{response.question_order}: {response.question.question_text}\nA: {transcript}")
                elif response.response_text:
                    transcript_parts.append(f"Q{response.question_order}: {response.question.question_text}\nA: {response.response_text}")

            full_transcript = "\n\n".join(transcript_parts)

            # Get voice confidence metrics
            voice_confidence_metrics = {}
            if assessment.voice_confidence_score:
                voice_confidence_metrics['score'] = assessment.voice_confidence_score
            # Add more voice metrics if available from speech analysis
            if responses.exists():
                first_speech = responses.first().analysis_data.get('speech_analysis', {}) if isinstance(responses.first().analysis_data, dict) else {}
                if isinstance(first_speech, dict):
                    if first_speech.get('speaking_rate'):
                        voice_confidence_metrics['pace'] = first_speech['speaking_rate']
                    if first_speech.get('fluency_score'):
                        voice_confidence_metrics['clarity'] = first_speech['fluency_score']

            # Get body language metrics from snapshots
            body_language_metrics = {}
            if assessment.body_language_score:
                body_language_metrics['posture_score'] = assessment.body_language_score
            # Extract detailed body language metrics if available
            body_snapshots = snapshots.filter(analysis_type='body_language')
            if body_snapshots.exists():
                bl_data = body_snapshots.first().analysis_data if isinstance(body_snapshots.first().analysis_data, dict) else {}
                if isinstance(bl_data, dict):
                    if bl_data.get('eye_contact_score'):
                        body_language_metrics['eye_contact_score'] = bl_data['eye_contact_score']
                    if bl_data.get('gesture_score'):
                        body_language_metrics['gesture_score'] = bl_data['gesture_score']

            # Get resume text if available (from session)
            resume_text = request.session.get(_resume_session_key(str(assessment.session_id)), '')

            # Generate AI coaching
            ai_coaching = generate_ai_interview_coach(
                interview_transcript=full_transcript,
                questions=questions_list,
                scores={
                    'overall_score': assessment.overall_score,
                    'speaking_score': assessment.speaking_score,
                    'body_language_score': assessment.body_language_score,
                    'attire_score': assessment.attire_score,
                },
                voice_confidence_metrics=voice_confidence_metrics if voice_confidence_metrics else None,
                body_language_metrics=body_language_metrics if body_language_metrics else None,
                resume_text=resume_text if resume_text else None,
                role=assessment.platform_job_title.title
            )

            if ai_coaching:
                assessment.ai_coach_summary = ai_coaching.get('summary')
                assessment.ai_coach_strengths = ai_coaching.get('strengths', [])
                assessment.ai_coach_weaknesses = ai_coaching.get('weaknesses', [])
                assessment.ai_coach_action_plan = ai_coaching.get('action_plan', {})
                assessment.ai_coach_recommended_topics = ai_coaching.get('recommended_topics', [])
                assessment.ai_coach_generated_at = timezone.now()
                assessment.ai_coach_status = 'generated'
                assessment.save(update_fields=[
                    'ai_coach_summary', 'ai_coach_strengths', 'ai_coach_weaknesses',
                    'ai_coach_action_plan', 'ai_coach_recommended_topics',
                    'ai_coach_generated_at', 'ai_coach_status'
                ])
                print(f"[AI Coach] Successfully generated coaching for assessment {assessment.session_id}")
            else:
                assessment.ai_coach_status = 'failed'
                assessment.save(update_fields=['ai_coach_status'])
                print(f"[AI Coach] Failed to generate coaching for assessment {assessment.session_id}")

        except Exception as e:
            assessment.ai_coach_status = 'failed'
            assessment.save(update_fields=['ai_coach_status'])
            print(f"[AI Coach] Error generating coaching: {e}")
            # Don't crash the assessment completion if coaching fails

    # Skill Gap Detection — one-shot Groq analysis of all responses (alongside AI Coach)
    if assessment.skill_gap_analysis is None:
        try:
            response_payloads = []
            for response in responses:
                analysis_data = response.analysis_data if isinstance(response.analysis_data, dict) else {}
                speech_analysis = analysis_data.get('speech_analysis', {}) if isinstance(analysis_data, dict) else {}
                transcript = ''
                if isinstance(speech_analysis, dict):
                    transcript = (
                        speech_analysis.get('transcription')
                        or speech_analysis.get('transcript')
                        or ''
                    )
                if not transcript and response.response_text:
                    transcript = response.response_text

                response_payloads.append({
                    'question_text': response.question.question_text if response.question_id else '',
                    'response_text': transcript or '',
                    'fluency_score': response.fluency_score,
                    'pronunciation_score': response.pronunciation_score,
                    'relevance_score': response.relevance_score,
                    'confidence_score': response.confidence_score,
                    'content_evaluation': analysis_data.get('content_evaluation', {}) if isinstance(analysis_data, dict) else {},
                })

            skill_gap_result = generate_skill_gap_analysis(
                job_role=assessment.platform_job_title.title if assessment.platform_job_title_id else '',
                response_payloads=response_payloads,
            )
            if skill_gap_result is not None:
                assessment.skill_gap_analysis = skill_gap_result
                assessment.save(update_fields=['skill_gap_analysis'])
                print(f"[Skill Gaps] Stored analysis for assessment {assessment.session_id}")
            else:
                # Persist empty shell so we do not retry Groq on every results page refresh
                assessment.skill_gap_analysis = {'skill_gaps': [], 'strengths': []}
                assessment.save(update_fields=['skill_gap_analysis'])
                logger.warning(
                    'Skill gap analysis unavailable for assessment %s — stored empty result',
                    assessment.session_id,
                )
        except Exception as e:
            logger.warning('Skill gap analysis error for assessment %s: %s', assessment.session_id, e)
            try:
                assessment.skill_gap_analysis = {'skill_gaps': [], 'strengths': []}
                assessment.save(update_fields=['skill_gap_analysis'])
            except Exception:
                pass
            # Do not block the completion page

    # Personalized Learning Roadmap — one-shot generation built upon skill gaps
    if assessment.learning_roadmap is None:
        try:
            skill_gaps_list = []
            if assessment.skill_gap_analysis and isinstance(assessment.skill_gap_analysis.get('skill_gaps'), list):
                skill_gaps_list = assessment.skill_gap_analysis['skill_gaps']
            
            roadmap_result = generate_learning_roadmap(
                job_role=assessment.platform_job_title.title if assessment.platform_job_title_id else '',
                skill_gaps=skill_gaps_list
            )
            if roadmap_result is not None:
                assessment.learning_roadmap = roadmap_result
                assessment.save(update_fields=['learning_roadmap'])
                print(f"[Learning Roadmap] Stored analysis for assessment {assessment.session_id}")
            else:
                assessment.learning_roadmap = {'weeks': []}
                assessment.save(update_fields=['learning_roadmap'])
                logger.warning(
                    'Learning roadmap unavailable for assessment %s — stored empty result',
                    assessment.session_id,
                )
        except Exception as e:
            logger.warning('Learning roadmap error for assessment %s: %s', assessment.session_id, e)
            try:
                assessment.learning_roadmap = {'weeks': []}
                assessment.save(update_fields=['learning_roadmap'])
            except Exception:
                pass

    # AI Communication Analysis — whole-assessment style analysis (one Groq call)
    # Triggered alongside AI Coach / Skill Gaps / Roadmap; guarded so it only runs once.
    if assessment.communication_analysis is None:
        try:
            comm_payloads = []
            for _resp in responses:
                _ad = _resp.analysis_data if isinstance(_resp.analysis_data, dict) else {}
                _sa = _ad.get('speech_analysis', {})
                _sa = _sa if isinstance(_sa, dict) else {}
                _vc = _ad.get('voice_confidence', {})
                _vc = _vc if isinstance(_vc, dict) else {}
                _fluency = _ad.get('fluency', {})
                _fluency = _fluency if isinstance(_fluency, dict) else {}

                # Prefer speech_analysis transcript, fall back to response_text
                transcript = (
                    _sa.get('transcription') or _sa.get('transcript') or _resp.response_text or ''
                )

                # Voice scores — already computed, just read from analysis_data
                fluency_score = _resp.fluency_score
                if fluency_score is not None and fluency_score <= 1:
                    fluency_score *= 10
                pronunciation_score = _resp.pronunciation_score
                if pronunciation_score is not None and pronunciation_score <= 1:
                    pronunciation_score *= 10
                confidence_score = _resp.confidence_score
                if confidence_score is not None and confidence_score <= 1:
                    confidence_score *= 10

                # Fluency sub-metrics from speech_analysis details
                _fluency_details = _sa.get('details', {}).get('fluency', {})
                if isinstance(_fluency_details, dict):
                    filler_count = _fluency_details.get('filler_count')
                    filler_ratio = _fluency_details.get('filler_ratio')
                    words_per_minute = _fluency_details.get('words_per_minute')
                else:
                    filler_count = filler_ratio = words_per_minute = None

                # Audio energy / pitch from speech_analysis details
                _audio_features = _sa.get('details', {}).get('audio_features', {})
                _audio_features = _audio_features if isinstance(_audio_features, dict) else {}
                raw_avg_energy = _audio_features.get('avg_energy')
                raw_pitch_var = _audio_features.get('pitch_variance')

                import math as _math
                avg_energy_norm = round(min(raw_avg_energy * 300, 100), 2) if raw_avg_energy is not None else None
                if raw_pitch_var is not None and raw_pitch_var > 0:
                    pitch_var_norm = round(min(_math.log1p(raw_pitch_var) / 15 * 100, 100), 2)
                elif raw_pitch_var == 0:
                    pitch_var_norm = 0.0
                else:
                    pitch_var_norm = None

                comm_payloads.append({
                    'question_text': _resp.question.question_text if _resp.question_id else '',
                    'response_text': transcript,
                    'fluency_score': fluency_score,
                    'pronunciation_score': pronunciation_score,
                    'confidence_score': confidence_score,
                    'filler_count': filler_count,
                    'filler_ratio': filler_ratio,
                    'words_per_minute': words_per_minute,
                    'speaking_rate': _sa.get('speaking_rate'),
                    'avg_energy': avg_energy_norm,
                    'pitch_variance': pitch_var_norm,
                })

            comm_result = generate_communication_analysis(
                job_role=assessment.platform_job_title.title if assessment.platform_job_title_id else '',
                response_payloads=comm_payloads,
            )
            if comm_result is not None:
                assessment.communication_analysis = comm_result
                assessment.save(update_fields=['communication_analysis'])
                print(f"[CommAnalysis] Stored for assessment {assessment.session_id}")
            else:
                # Persist empty shell so we skip on every subsequent page refresh
                assessment.communication_analysis = {'summary': '', 'traits': []}
                assessment.save(update_fields=['communication_analysis'])
                logger.warning(
                    'Communication analysis unavailable for assessment %s — stored empty result',
                    assessment.session_id,
                )
        except Exception as _comm_err:
            logger.exception(
                'Communication analysis error for assessment %s',
                assessment.session_id,
            )
            try:
                assessment.communication_analysis = {'summary': '', 'traits': []}
                assessment.save(update_fields=['communication_analysis'])
            except Exception:
                pass
            # Must not block the completion page

    # ── Trigger CV Analysis automatically ────────────────────────────────
    if assessment.cv_analysis_status == 'pending' and not assessment.cv_analysis_events:
        assessment.cv_analysis_status = 'pending'
        assessment.save(update_fields=['cv_analysis_status'])
        from .tasks import process_cv_analysis_task
        try:
            from django_q.tasks import async_task
            async_task(process_cv_analysis_task, assessment.id, timeout=600)
            logger.info(f"[CV Analysis] Queued task via django-q for assessment {assessment.session_id}")
        except Exception as e:
            logger.error(f"[CV Analysis] django-q enqueue failed ({e}), using thread fallback")
            import threading
            thread = threading.Thread(target=process_cv_analysis_task, args=(assessment.id,), daemon=True)
            thread.start()

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
    
    # Feature #24 hook: if this assessment was part of a placement drive, redirect to advance
    if request.session.get('active_placement_drive_id'):
        return redirect('analysis:placement_drive_advance')

    # Feature #25 — Panel data for result screen
    panel_session = None
    if assessment.interview_mode == 'panel':
        try:
            panel_session = assessment.panel_session
        except:
            pass

    context = {
        'assessment': assessment,
        'job_title': assessment.platform_job_title,
        'responses': responses,
        'snapshots': snapshots,
        'ai_feedback_summary': ai_feedback_summary,
        'panel_session': panel_session,
        'duration_seconds': int((assessment.completed_at - assessment.started_at).total_seconds()) if assessment.completed_at and assessment.started_at else 0,
        'duration_minutes': int((assessment.completed_at - assessment.started_at).total_seconds() // 60) if assessment.completed_at and assessment.started_at else 0,
        'confidence_chart_json': confidence_chart_json,
        'energy_insight': energy_insight,
        'has_chart_data': bool(valid_energy),
        'platform_average': platform_average,
        'communication_analysis': assessment.communication_analysis,
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
    avg_score  = round(stats['avg_score'],  1) if stats['avg_score'] is not None else None
    best_score = round(stats['best_score'], 1) if stats['best_score'] is not None else None
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
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        assessment = get_object_or_404(
            IndividualAssessment,
            session_id=session_id
        )
        
        question_id = data.get('question_id')
        audio_data = data.get('audio_data', '')
        video_file = request.FILES.get('video_file')
        response_time = int(data.get('response_time', 0))
        fullscreen_violations = int(data.get('fullscreen_violations', 0))
        
        # Get question
        question = get_object_or_404(PlatformQuestion, id=question_id)
        
        # Save basic response
        response = IndividualAssessmentResponse.objects.create(
            assessment=assessment,
            question=question,
            question_order=IndividualAssessmentResponse.objects.filter(assessment=assessment).count() + 1,
            question_started_at=timezone.now(),
            response_started_at=timezone.now(),
            response_ended_at=timezone.now(),
            response_duration=response_time,
            time_to_start=0,
            analysis_data={
                'fullscreen_violations': fullscreen_violations,
                'speech_analysis_status': 'pending' if (audio_data or video_file) else 'not_applicable'
            }
        )
        
        # Perform speech analysis in background
        if video_file:
            try:
                filename = f"response_{assessment.id}_{assessment.current_question_index + 1}_{uuid.uuid4().hex[:8]}.webm"
                response.video_file.save(filename, video_file)
            except Exception as e:
                print(f"Video storage failed: {e}")
        elif audio_data:
            is_valid, error_msg = validate_audio_b64(audio_data)
            if not is_valid:
                return JsonResponse({'success': False, 'error': error_msg}, status=400)
            
            audio_len = len(audio_data)
            est_bytes = int(audio_len * 3 / 4)
            response.analysis_data['audio_b64_length'] = audio_len
            response.analysis_data['audio_est_bytes'] = est_bytes
            response.save(update_fields=['analysis_data'])
                
        if (video_file or audio_data) and SPEECH_ANALYSIS_AVAILABLE:
            _enqueue_speech_analysis(response.id, question.question_text)
        
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
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST.dict()
        
        assessment = get_object_or_404(
            IndividualAssessment,
            session_id=session_id
        )
        
        question_id = data.get('question_id')
        audio_data = data.get('audio_data', '')
        video_file = request.FILES.get('video_file')
        response_time = int(data.get('response_time', 0))
        fullscreen_violations = int(data.get('fullscreen_violations', 0))
        
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
            'has_audio_data': bool(audio_data) or bool(video_file)
        }
        
        # Set speech analysis status if we have audio/video
        if (audio_data or video_file) and SPEECH_ANALYSIS_AVAILABLE:
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
        
        # Handle audio/video data if provided
        if video_file:
            try:
                filename = f"response_{assessment.id}_{assessment.current_question_index + 1}_{uuid.uuid4().hex[:8]}.webm"
                response.video_file.save(filename, video_file)
            except Exception as e:
                print(f"Video storage failed: {e}")
        elif audio_data:
            is_valid, error_msg = validate_audio_b64(audio_data)
            if not is_valid:
                return JsonResponse({'success': False, 'error': error_msg}, status=400)
            try:
                audio_len = len(audio_data)
                est_bytes = int(audio_len * 3 / 4)
                response.analysis_data['audio_b64_length'] = audio_len
                response.analysis_data['audio_est_bytes'] = est_bytes
                response.save(update_fields=['analysis_data'])
            except Exception as e:
                print(f"Audio storage failed: {e}")
        
        # Start speech analysis in background (don't wait for it)
        if (video_file or audio_data) and SPEECH_ANALYSIS_AVAILABLE:
            _enqueue_speech_analysis(response.id, question.question_text)
        
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
        # Ready when nothing remains 'pending'. Terminal states
        # (completed / failed / error / not_applicable / not_available) all count as done.
        processing_complete = pending_responses == 0
        
        # Log for debugging
        print(f"Processing status: {pending_responses} pending, {failed_responses} failed, out of {total_responses} total")
        
        return JsonResponse({
            'success': True,
            'ready': processing_complete,
            'processing_complete': processing_complete,
            'pending_count': pending_responses,
            'failed_count': failed_responses,
            'total_responses': total_responses,
            'progress_percentage': ((total_responses - pending_responses) / max(total_responses, 1)) * 100
        })
        
    except Exception as e:
        print(f"Processing status check failed: {e}")
        return JsonResponse({'success': False, 'error': str(e), 'ready': False})


@login_required
def processing_interstitial(request, session_id):
    """Show processing interstitial page while analysis completes in background"""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user
    )
    
    context = {
        'assessment': assessment,
        'session_id': session_id,
    }
    return render(request, 'analysis/processing_interstitial.html', context)


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
    
    # Generate a badge specific to this assessment
    badge_data = {
        'user_name': request.user.get_full_name() or request.user.username,
        'achievement_title': f"{assessment.platform_job_title.title} Pro",
        'achievement_description': f"Successfully completed the {assessment.platform_job_title.title} assessment.",
        'achievement_icon': '🎓',
        'date': assessment.completed_at
    }
    
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
    
    # Generate a badge specific to this assessment
    badge_data = {
        'user_name': request.user.get_full_name() or request.user.username,
        'achievement_title': f"{assessment.platform_job_title.title} Pro",
        'achievement_description': f"Successfully completed the {assessment.platform_job_title.title} assessment.",
        'achievement_icon': '🎓',
        'date': assessment.completed_at
    }
    
    if not badge_data:
        messages.error(request, "No achievements unlocked yet.")
        return redirect('analysis:individual_assessment_complete', session_id=session_id)
    
    # Generate badge as HTML then convert to PDF via xhtml2pdf
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    import io
    import logging
    logger = logging.getLogger(__name__)

    html_string = render_to_string('analysis/badge_image.html', {
        'badge_data': badge_data,
        'assessment': assessment,
    })

    # Create PDF
    result = io.BytesIO()
    pdf = pisa.pisaDocument(
        io.BytesIO(html_string.encode('utf-8')),
        result,
        encoding='utf-8'
    )

    if not pdf.err:
        result.seek(0)
        response = HttpResponse(result.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="persona_achievement_{session_id}.pdf"'
        return response

    logger.error('xhtml2pdf badge generation error for session %s: %s', session_id, pdf.err)
    messages.error(request, "Error generating badge PDF. Please try again.")
    return redirect('analysis:achievement_badge', session_id=session_id)


@login_required
def export_institution_members_csv(request):
    """Export institution members and their assessment results as CSV"""
    if not hasattr(request.user, 'business_profile'):
        messages.error(request, "Access denied. Only business users can access this page.")
        return redirect('persona_frontend:home')
    
    business_user = request.user.business_profile
    
    # Get institution members
    from UserAPI.models import InstitutionMembership
    institution_members = InstitutionMembership.objects.filter(
        business=business_user,
        is_active=True
    ).select_related('individual__user')
    
    # Get member assessments
    from AnalysisAPI.models import IndividualAssessment
    member_assessments = IndividualAssessment.objects.filter(
        institution_membership__business=business_user,
        institution_membership__is_active=True,
        status='completed'
    ).select_related('platform_job_title', 'institution_membership__individual__user')
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="institution_members_{business_user.company_name or business_user.name}_{timezone.now().date()}.csv"'
    
    writer = csv.writer(response)
    
    # Write header
    writer.writerow([
        'Name',
        'Email',
        'Joined Date',
        'Consent Granted',
        'Total Assessments',
        'Average Score',
        'Best Score',
        'Last Assessment Date'
    ])
    
    # Write member data
    for membership in institution_members:
        individual = membership.individual
        user = individual.user
        
        # Get assessment stats for this member
        assessments = member_assessments.filter(
            institution_membership=membership
        )
        
        total_assessments = assessments.count()
        avg_score = None
        best_score = None
        last_date = None
        
        if assessments.exists():
            scores = [a.overall_score for a in assessments if a.overall_score]
            if scores:
                avg_score = sum(scores) / len(scores)
                best_score = max(scores)
            last_date = assessments.order_by('-completed_at').first().completed_at
        
        writer.writerow([
            individual.name,
            user.email,
            membership.joined_at.strftime('%Y-%m-%d'),
            'Yes' if membership.consent_granted else 'No',
            total_assessments,
            f"{avg_score:.1f}" if avg_score else 'N/A',
            f"{best_score:.1f}" if best_score else 'N/A',
            last_date.strftime('%Y-%m-%d') if last_date else 'N/A'
        ])
    
    return response


# =====================================
# RESUME REVIEWER VIEWS
# =====================================
from .models import ResumeReview
from AnalysisModules.feedback_generator import _call_groq
import json
import hashlib

@login_required
def resume_reviewer_upload(request):
    if request.method == 'POST':
        resume_file = request.FILES.get('resume_file')
        if not resume_file:
            messages.error(request, 'Please upload a resume file.')
            return redirect('analysis:resume_reviewer_upload')
            
        is_valid, error_msg = _validate_resume_upload(resume_file)
        if not is_valid:
            messages.error(request, error_msg)
            return redirect('analysis:resume_reviewer_upload')
            
        # --- Compute SHA-256 hash of file bytes for deduplication ---
        resume_file.seek(0)
        file_bytes = resume_file.read()
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        
        # --- Check for duplicate upload by same user ---
        existing_review = ResumeReview.objects.filter(
            user=request.user,
            file_hash=file_hash
        ).first()
        
        if existing_review:
            # Duplicate detected: redirect to existing result with friendly message
            from django.utils import timezone
            upload_date = existing_review.created_at.strftime('%B %d, %Y')
            messages.info(
                request,
                f"You've already analyzed this exact resume on {upload_date}. "
                "Showing your previous results below. Want a fresh analysis? "
                "Delete this entry first, then re-upload."
            )
            return redirect('analysis:resume_reviewer_result', review_id=existing_review.id)
            
        # --- Determine version number for this upload ---
        from django.db.models import Max
        max_version = ResumeReview.objects.filter(user=request.user).aggregate(
            Max('version_number')
        )['version_number__max']
        next_version = (max_version or 0) + 1

        # Save placeholder row with file hash
        review = ResumeReview.objects.create(
            user=request.user,
            resume_file=resume_file,
            overall_score=0,
            feedback={},
            version_number=next_version,
            file_hash=file_hash,
        )
        
        # Extract text
        try:
            resume_text = _extract_resume_text(resume_file)
        except Exception as e:
            review.feedback = {"error": f"Failed to extract text from resume: {str(e)}"}
            review.save()
            return redirect('analysis:resume_reviewer_result', review_id=review.id)
            
        if not resume_text or not resume_text.strip():
            review.feedback = {"error": "No text could be extracted from the file."}
            review.save()
            return redirect('analysis:resume_reviewer_result', review_id=review.id)
            
        # --- Call 1: Overall score & feedback ---
        prompt = (
            "You are an expert ATS and recruiter. Review the following resume and provide feedback. "
            "Respond ONLY with a valid JSON object matching exactly this structure, no markdown formatting or extra text:\n"
            "{\n"
            '  "overall_score": float (0-10),\n'
            '  "feedback": {\n'
            '    "strengths": ["list of strings"],\n'
            '    "weaknesses": ["list of strings"],\n'
            '    "suggestions": ["list of strings"]\n'
            "  }\n"
            "}\n\n"
            f"RESUME TEXT:\n{resume_text}"
        )
        
        try:
            response_text = _call_groq(prompt, timeout=45)
            if not response_text:
                raise ValueError("Empty response from Groq")
            
            # Parse JSON. Strip markdown if Groq hallucinates it
            response_text = response_text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
                
            data = json.loads(response_text.strip())
            
            review.overall_score = float(data.get('overall_score', 0))
            review.feedback = data.get('feedback', {})
        except Exception as e:
            review.feedback = {"error": "Analysis failed, please try again"}

        # --- Call 2: ATS Score & feedback (isolated — failure here does NOT affect Call 1) ---
        ats_prompt = (
            "You are an expert Applicant Tracking System (ATS) specialist. "
            "Analyse the following resume strictly from an ATS perspective. "
            "Respond ONLY with a valid JSON object matching exactly this structure, no markdown or extra text:\n"
            "{\n"
            '  "ats_score": float (0-100, how well the resume would pass an ATS scan),\n'
            '  "ats_feedback": {\n'
            '    "keyword_gaps": ["list of important keywords missing from the resume"],\n'
            '    "formatting_issues": ["list of formatting problems that hurt ATS parsing"],\n'
            '    "recommendations": ["list of concrete steps to improve the ATS score"]\n'
            "  }\n"
            "}\n\n"
            f"RESUME TEXT:\n{resume_text}"
        )

        try:
            ats_response_text = _call_groq(ats_prompt, timeout=45)
            if not ats_response_text:
                raise ValueError("Empty ATS response from Groq")

            ats_response_text = ats_response_text.strip()
            if ats_response_text.startswith('```json'):
                ats_response_text = ats_response_text[7:]
            if ats_response_text.startswith('```'):
                ats_response_text = ats_response_text[3:]
            if ats_response_text.endswith('```'):
                ats_response_text = ats_response_text[:-3]

            ats_data = json.loads(ats_response_text.strip())

            review.ats_score = float(ats_data.get('ats_score', 0))
            review.ats_feedback = ats_data.get('ats_feedback', {})
        except Exception:
            # Graceful degradation: ATS failure never blocks overall review
            review.ats_score = None
            review.ats_feedback = {"error": "ATS analysis unavailable"}

        review.save()
        return redirect('analysis:resume_reviewer_result', review_id=review.id)
        
    return render(request, 'analysis/resume_reviewer_upload.html')

@login_required
def resume_reviewer_result(request, review_id):
    from django.http import Http404
    review = get_object_or_404(ResumeReview, id=review_id)
    if review.user != request.user:
        raise Http404("Not found")

    total_reviews = ResumeReview.objects.filter(user=request.user).count()
    return render(request, 'analysis/resume_reviewer_result.html', {
        'review': review,
        'total_reviews': total_reviews,
    })

@login_required
def resume_reviewer_history(request):
    # Fetch all reviews ordered newest-first for display
    reviews_qs = list(
        ResumeReview.objects.filter(user=request.user).order_by('-version_number')
    )

    # Build a version_number → overall_score lookup for delta computation
    score_by_version = {r.version_number: r.overall_score for r in reviews_qs}

    # Annotate each review with its score delta vs the previous version
    annotated = []
    for review in reviews_qs:
        prev_score = score_by_version.get(review.version_number - 1)
        if prev_score is not None:
            delta = round(review.overall_score - prev_score, 2)
        else:
            delta = None  # first version — no comparison
        annotated.append({'review': review, 'delta': delta})

    return render(request, 'analysis/resume_reviewer_history.html', {
        'annotated_reviews': annotated,
    })


# =====================================
# COVER LETTER GENERATOR VIEWS
# =====================================
from .models import CoverLetter

@login_required
def cover_letter_generate(request):
    if request.method == 'POST':
        job_title = request.POST.get('job_title')
        company_name = request.POST.get('company_name', '')
        job_description = request.POST.get('job_description', '')
        resume_review_id = request.POST.get('resume_review_id')

        if not job_title:
            messages.error(request, 'Job title is required.')
            return redirect('analysis:cover_letter_generate')

        resume_context = ""
        resume_review = None
        file_hash = None
        if resume_review_id:
            try:
                resume_review = ResumeReview.objects.get(id=resume_review_id, user=request.user)
                resume_context = _extract_resume_text(resume_review.resume_file)
                
                # --- Compute SHA-256 hash of file bytes for deduplication ---
                resume_review.resume_file.seek(0)
                file_bytes = resume_review.resume_file.read()
                file_hash = hashlib.sha256(file_bytes).hexdigest()
                
                # --- Check for duplicate cover letter by same user with same resume ---
                existing_letter = CoverLetter.objects.filter(
                    user=request.user,
                    file_hash=file_hash,
                    job_title=job_title,
                    company_name=company_name,
                ).first()
                
                if existing_letter:
                    messages.info(request, 'You already have a cover letter for this job with the same resume. Redirecting to your existing cover letter.')
                    return redirect('analysis:cover_letter_result', letter_id=existing_letter.id)
                    
            except ResumeReview.DoesNotExist:
                messages.error(request, 'Selected resume review not found.')
                return redirect('analysis:cover_letter_generate')
            except Exception as e:
                messages.error(request, f'Failed to extract resume text: {str(e)}')
                return redirect('analysis:cover_letter_generate')

        prompt = (
            "You are an expert career coach and professional copywriter. "
            "Write a compelling, professional cover letter for the following job.\n\n"
            f"Job Title: {job_title}\n"
        )
        if company_name:
            prompt += f"Company Name: {company_name}\n"
        if job_description:
            prompt += f"Job Description:\n{job_description}\n"
        if resume_context:
            prompt += f"\nApplicant's Resume Context:\n{resume_context}\n"
        
        prompt += (
            "\nOutput ONLY the cover letter text. Do not include markdown formatting like ``` or introductory/concluding remarks."
        )

        try:
            generated_text = _call_groq(prompt, timeout=45)
            if not generated_text:
                raise ValueError("Empty response from Groq")
            
            # Clean up potential markdown formatting
            generated_text = generated_text.strip()
            if generated_text.startswith('```'):
                lines = generated_text.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines[-1].startswith('```'):
                    lines = lines[:-1]
                generated_text = '\n'.join(lines).strip()

            cover_letter = CoverLetter.objects.create(
                user=request.user,
                job_title=job_title,
                company_name=company_name,
                job_description=job_description,
                resume_review=resume_review,
                generated_text=generated_text,
                file_hash=file_hash
            )
            return redirect('analysis:cover_letter_result', letter_id=cover_letter.id)
            
        except Exception as e:
            messages.error(request, 'Failed to generate cover letter. Please try again.')
            return redirect('analysis:cover_letter_generate')

    # GET request
    resume_reviews = ResumeReview.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'analysis/cover_letter_generate.html', {
        'resume_reviews': resume_reviews
    })

@login_required
def cover_letter_result(request, letter_id):
    from django.http import Http404
    cover_letter = get_object_or_404(CoverLetter, id=letter_id)
    if cover_letter.user != request.user:
        raise Http404("Not found")

    return render(request, 'analysis/cover_letter_result.html', {
        'cover_letter': cover_letter,
    })

@login_required
def cover_letter_history(request):
    cover_letters = CoverLetter.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'analysis/cover_letter_history.html', {
        'cover_letters': cover_letters,
    })


# =====================================
# LINKEDIN POST GENERATOR VIEWS
# =====================================
from .models import LinkedInPost

@login_required
def linkedin_post_generate(request):
    if request.method == 'POST':
        topic = request.POST.get('topic')
        tone = request.POST.get('tone', 'professional')
        resume_review_id = request.POST.get('resume_review_id')

        if not topic:
            messages.error(request, 'Topic is required.')
            return redirect('analysis:linkedin_post_generate')

        resume_context = ""
        resume_review = None
        if resume_review_id:
            try:
                resume_review = ResumeReview.objects.get(id=resume_review_id, user=request.user)
                resume_context = _extract_resume_text(resume_review.resume_file)
            except ResumeReview.DoesNotExist:
                messages.error(request, 'Selected resume review not found.')
                return redirect('analysis:linkedin_post_generate')
            except Exception as e:
                messages.error(request, f'Failed to extract resume text: {str(e)}')
                return redirect('analysis:linkedin_post_generate')

        prompt = (
            "You are an expert personal branding consultant and social media manager. "
            f"Write an engaging LinkedIn post about the following topic: {topic}\n"
            f"The tone of the post should be: {tone}.\n"
        )
        if resume_context:
            prompt += f"\nUse the following resume context to make the post highly personalized and relevant to the author's background:\n{resume_context}\n"
        
        prompt += (
            "\nOutput ONLY the text of the LinkedIn post. Do not include any introductory remarks, "
            "concluding remarks, or markdown code block formatting (like ```). Include relevant emojis and hashtags."
        )

        try:
            generated_text = _call_groq(prompt, timeout=45)
            if not generated_text:
                raise ValueError("Empty response from Groq")
            
            # Clean up potential markdown formatting
            generated_text = generated_text.strip()
            if generated_text.startswith('```'):
                lines = generated_text.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines[-1].startswith('```'):
                    lines = lines[:-1]
                generated_text = '\n'.join(lines).strip()

            linkedin_post = LinkedInPost.objects.create(
                user=request.user,
                topic=topic,
                tone=tone,
                resume_review=resume_review,
                generated_text=generated_text
            )
            return redirect('analysis:linkedin_post_result', post_id=linkedin_post.id)
            
        except Exception as e:
            messages.error(request, 'Failed to generate LinkedIn post. Please try again.')
            return redirect('analysis:linkedin_post_generate')

    # GET request
    resume_reviews = ResumeReview.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'analysis/linkedin_post_generate.html', {
        'resume_reviews': resume_reviews
    })

@login_required
def linkedin_post_result(request, post_id):
    from django.http import Http404
    post = get_object_or_404(LinkedInPost, id=post_id)
    if post.user != request.user:
        raise Http404("Not found")

    return render(request, 'analysis/linkedin_post_result.html', {
        'post': post,
    })

@login_required
def linkedin_post_history(request):
    posts = LinkedInPost.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'analysis/linkedin_post_history.html', {
        'posts': posts,
    })


# =====================================
# INTERVIEW SUMMARY VIDEO VIEWS
# =====================================

@login_required
@require_http_methods(["POST"])
def interview_summary_video_generate(request):
    """Generate a summary video for an assessment via POST."""
    from .models import InterviewSummaryVideo

    assessment_id = request.POST.get('assessment_id')
    if not assessment_id:
        return JsonResponse({'error': 'assessment_id is required'}, status=400)

    assessment = get_object_or_404(
        IndividualAssessment,
        id=assessment_id,
        user=request.user,
    )

    # Guard: if a pending or processing record already exists, reuse it
    # instead of spawning a duplicate worker that would race the first.
    existing = InterviewSummaryVideo.objects.filter(
        assessment=assessment,
        user=request.user,
        status__in=['pending', 'processing'],
    ).order_by('-created_at').first()
    if existing:
        return redirect('analysis:interview_summary_video_result', video_id=existing.id)

    # Create InterviewSummaryVideo record
    video_record = InterviewSummaryVideo.objects.create(
        assessment=assessment,
        user=request.user,
        status='pending'
    )

    # Enqueue background task using django-q pattern
    from .tasks import generate_summary_video_task
    try:
        from django_q.tasks import async_task
        logger.info(f"[SUMMARY VIDEO] Attempting to enqueue task for video_record {video_record.id}")
        task_id = async_task(
            generate_summary_video_task,
            video_record.id,
            timeout=300,  # per-task timeout: 5 min, overrides Q_CLUSTER global of 60 s
        )
        logger.info(f"[SUMMARY VIDEO] Task enqueued successfully with task_id: {task_id}")
    except Exception as e:
        logger.error(f"[SUMMARY VIDEO] django-q enqueue failed ({e}), using thread fallback")
        print(f"django-q enqueue failed ({e}), using thread fallback")
        import threading
        thread = threading.Thread(
            target=generate_summary_video_task,
            args=(video_record.id,),
            daemon=True,
        )
        thread.start()
        logger.info(f"[SUMMARY VIDEO] Thread fallback started for video_record {video_record.id}")

    return redirect('analysis:interview_summary_video_result', video_id=video_record.id)


@login_required
@require_http_methods(["GET"])
def interview_summary_video_status(request, video_id):
    """Check the status of a summary video generation. Returns JSON."""
    from .models import InterviewSummaryVideo

    video_record = get_object_or_404(
        InterviewSummaryVideo,
        id=video_id,
        user=request.user,
    )

    response_data = {
        'success': True,
        'status': video_record.status,
    }

    if video_record.status == 'completed' and video_record.video_file:
        response_data['video_url'] = video_record.video_file.url
    elif video_record.status == 'failed':
        response_data['error_message'] = video_record.error_message

    return JsonResponse(response_data)


@login_required
@require_http_methods(["GET"])
def interview_summary_video_result(request, video_id):
    """Render the video result page with player or loading state."""
    from .models import InterviewSummaryVideo

    video_record = get_object_or_404(
        InterviewSummaryVideo,
        id=video_id,
        user=request.user
    )

    context = {
        'video_record': video_record,
        'assessment': video_record.assessment,
    }
    return render(request, 'analysis/interview_summary_video_result.html', context)


# =============================================================================
# Feature #18: CV Interview Replay with AI Timeline Annotations
# =============================================================================

@login_required
@require_http_methods(["GET"])
def cv_replay(request, session_id):
    """
    Render the CV interview replay page.

    Shows per-question video players with clickable CV-event timelines.
    CV scores and events are now stored on IndividualAssessment (not AssessmentResult).
    Each IndividualAssessmentResponse has its own video file, and events are tagged
    with response_id/question_order to group them per question.
    """
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user,
    )

    # Get all responses with video files, ordered by question_order
    responses = assessment.responses.exclude(
        video_file=''
    ).exclude(
        video_file__isnull=True
    ).select_related('question').order_by('question_order')

    # Group events by response_id for template rendering
    events_by_response = {}
    if assessment.cv_analysis_events:
        for event in assessment.cv_analysis_events:
            response_id = event.get('response_id')
            if response_id:
                if response_id not in events_by_response:
                    events_by_response[response_id] = []
                events_by_response[response_id].append(event)

    context = {
        'assessment': assessment,
        'responses': responses,
        'events_by_response': events_by_response,
        # Pre-serialise events so the template can embed them as inline JSON
        'cv_events_json': json.dumps(assessment.cv_analysis_events or []),
        'cv_analysis_status': assessment.cv_analysis_status,
        'eye_contact_score': assessment.eye_contact_score,
        'posture_score': assessment.posture_score,
        'gesture_score': assessment.gesture_score,
    }
    return render(request, 'analysis/cv_replay.html', context)


@login_required
@require_http_methods(["GET"])
def cv_events_api(request, session_id):
    """
    Lightweight JSON endpoint — returns cv_analysis_events for a given session.

    Response schema:
        {
            "status": "completed" | "pending" | "processing" | "failed",
            "events": [{"response_id": int, "question_order": int, "timestamp_sec": int, "type": str}, ...],
            "scores": {
                "eye_contact": float | null,
                "posture": float | null,
                "distraction": float | null
            },
            "responses": [
                {
                    "id": int,
                    "question_order": int,
                    "question_text": str,
                    "video_url": str
                },
                ...
            ]
        }
    """
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user,
    )

    # Get all responses with video files
    responses_data = []
    responses = assessment.responses.exclude(
        video_file=''
    ).exclude(
        video_file__isnull=True
    ).select_related('question').order_by('question_order')

    for response in responses:
        try:
            video_url = response.video_file.url
        except Exception:
            video_url = None

        responses_data.append({
            'id': response.id,
            'question_order': response.question_order,
            'question_text': response.question.question_text,
            'video_url': video_url,
        })

    return JsonResponse({
        'status': assessment.cv_analysis_status,
        'events': assessment.cv_analysis_events or [],
        'scores': {
            'eye_contact': assessment.eye_contact_score,
            'posture': assessment.posture_score,
            'distraction': assessment.gesture_score,
        },
        'responses': responses_data,
    })


# =====================================
# DELETE VIEWS
# =====================================

@login_required
@require_http_methods(["POST"])
def delete_individual_assessment(request, session_id):
    """Delete an individual assessment and all its associated files."""
    assessment = get_object_or_404(
        IndividualAssessment,
        session_id=session_id,
        user=request.user
    )
    assessment.delete()
    return JsonResponse({'success': True})


@login_required
@require_http_methods(["POST"])
def delete_linkedin_post(request, post_id):
    """Delete a LinkedIn post."""
    post = get_object_or_404(
        LinkedInPost,
        id=post_id,
        user=request.user
    )
    post.delete()
    return JsonResponse({'success': True})


@login_required
@require_http_methods(["POST"])
def delete_resume_review(request, review_id):
    """Delete a resume review and its associated resume file."""
    review = get_object_or_404(
        ResumeReview,
        id=review_id,
        user=request.user
    )
    review.delete()
    return JsonResponse({'success': True})


@login_required
@require_http_methods(["POST"])
def delete_cover_letter(request, letter_id):
    """Delete a cover letter."""
    letter = get_object_or_404(
        CoverLetter,
        id=letter_id,
        user=request.user
    )
    letter.delete()
    return JsonResponse({'success': True})

@login_required
def generate_job_matches_api(request):
    """Feature #19 — AI Job Matching API endpoint.
    
    Returns a ranked list of job roles that best match this candidate,
    derived from their latest resume review + up to 3 recent assessments.
    Caches the result keyed on a data-hash so Groq is only re-called when
    the underlying data has actually changed (or the user forces a refresh).
    """
    import json as _json
    from django.http import JsonResponse
    from django.core.cache import cache
    from AnalysisAPI.models import ResumeReview, IndividualAssessment, PlatformJobTitle
    from AnalysisModules.feedback_generator import generate_job_matches
    import logging
    logger = logging.getLogger(__name__)

    user = request.user
    force_refresh = request.GET.get('refresh', 'false').lower() == 'true'

    try:
        latest_resume = ResumeReview.objects.filter(user=user).order_by('-created_at').first()
        latest_assessments = list(
            IndividualAssessment.objects.filter(user=user, status='completed').order_by('-created_at')[:3]
        )
        
        # Empty state: no data at all — do not call Groq
        if not latest_resume and not latest_assessments:
            return JsonResponse({
                'success': False, 
                'error': 'not_enough_data',
                'message': 'Complete an assessment or upload a resume to see your personalised job matches.'
            }, status=200)  # 200 so the frontend can display the friendly message cleanly

        # Build a deterministic hash from the IDs of the data we are using.
        # If this hash matches the cached entry we skip the Groq call.
        data_hash = (
            f"res_{latest_resume.id if latest_resume else 'none'}"
            f"_ast_{'_'.join(str(a.id) for a in latest_assessments)}"
        )
        cache_key = f"user_{user.id}_job_matches_v1"
        
        if not force_refresh:
            cached_data = cache.get(cache_key)
            if cached_data and cached_data.get('data_hash') == data_hash:
                return JsonResponse({'success': True, 'matches': cached_data['matches'], 'cached': True})

        # Build the candidate context string for the Groq prompt
        context_lines = []
        if latest_resume:
            context_lines.append(f"Resume Review Score: {latest_resume.overall_score}/100")
            if latest_resume.feedback:
                context_lines.append(f"Resume Feedback: {_json.dumps(latest_resume.feedback)[:500]}")
                
        if latest_assessments:
            context_lines.append("Recent Interview Assessments:")
            for a in latest_assessments:
                context_lines.append(f"- Role: {a.platform_job_title.title}, Score: {a.overall_score}/100")
                if a.ai_coach_strengths:
                    context_lines.append(f"  Strengths: {', '.join(a.ai_coach_strengths[:3])}")
                if a.ai_coach_weaknesses:
                    context_lines.append(f"  Weaknesses: {', '.join(a.ai_coach_weaknesses[:3])}")
                if a.skill_gap_analysis and isinstance(a.skill_gap_analysis, dict):
                    gaps = a.skill_gap_analysis.get('gaps', [])
                    if gaps:
                        context_lines.append(f"  Skill Gaps: {', '.join(g.get('skill','') for g in gaps[:3] if isinstance(g,dict))}")
                    
        candidate_context = "\n".join(context_lines)
        
        jobs = list(PlatformJobTitle.objects.filter(is_active=True).values_list('title', flat=True))
        if not jobs:
            logger.error("generate_job_matches_api: no active PlatformJobTitle records found")
            return JsonResponse({'success': False, 'error': 'no_job_titles', 'message': 'No active job titles found on the platform.'}, status=500)
            
        matches = generate_job_matches(candidate_context, jobs)
        if not matches:
            logger.warning("generate_job_matches_api: generate_job_matches returned None/empty")
            return JsonResponse({
                'success': False, 
                'error': 'ai_failed',
                'message': 'We could not generate job matches right now. Please try again in a moment.'
            }, status=200)  # 200 so the UI shows the message rather than treating it as a network failure
            
        result_data = {'data_hash': data_hash, 'matches': matches}
        cache.set(cache_key, result_data, timeout=86400 * 7)  # Cache for 7 days
        
        return JsonResponse({'success': True, 'matches': matches, 'cached': False})
        
    except Exception as exc:
        import traceback as _tb
        logger.error(f"generate_job_matches_api: unexpected error: {exc}\n{_tb.format_exc()}")
        return JsonResponse({
            'success': False,
            'error': 'server_error',
            'message': 'An unexpected error occurred. Please try again later.'
        }, status=500)


@login_required
def placement_readiness_api(request):
    """Feature #20 — Placement Readiness Predictor API endpoint."""
    import json as _json
    from django.http import JsonResponse
    from django.core.cache import cache
    from AnalysisAPI.models import ResumeReview, IndividualAssessment
    from AnalysisModules.readiness_predictor import calculate_placement_readiness
    from AnalysisModules.feedback_generator import _call_groq
    import re
    import logging
    
    logger = logging.getLogger(__name__)
    user = request.user
    force_refresh = request.GET.get('refresh', 'false').lower() == 'true'
    
    try:
        # Calculate the deterministic score
        readiness_data = calculate_placement_readiness(user)
        
        if not readiness_data.get('has_data'):
            return JsonResponse({
                'success': False,
                'error': 'not_enough_data',
                'message': 'Complete at least one assessment to see your placement readiness score.'
            }, status=200)

        # Build a deterministic hash from the assessments and resume used
        latest_resume = ResumeReview.objects.filter(user=user).order_by('-created_at').first()
        latest_assessments = list(
            IndividualAssessment.objects.filter(user=user, status='completed').order_by('-completed_at')[:5]
        )
        data_hash = (
            f"res_{latest_resume.id if latest_resume else 'none'}"
            f"_ast_{'_'.join(str(a.id) for a in latest_assessments)}"
        )
        cache_key = f"user_{user.id}_placement_readiness_v1"
        
        if not force_refresh:
            cached_data = cache.get(cache_key)
            if cached_data and cached_data.get('data_hash') == data_hash:
                return JsonResponse({
                    'success': True,
                    'readiness': cached_data['readiness'],
                    'cached': True
                })

        # Generate Readiness Insight using Groq
        prompt = (
            "You are an expert career coach. Based on the candidate's placement readiness score "
            "and breakdown, write a short 2-3 sentence personalized insight explaining their readiness "
            "for real job interviews and what they should focus on next.\n\n"
            f"Total Score: {readiness_data['total_score']}/100\n"
            f"Tier: {readiness_data['tier']}\n"
            f"Breakdown:\n"
        )
        for key, val in readiness_data['breakdown'].items():
            prompt += f"- {key}: {val['score']}/{val['max']} ({val['description']})\n"
            
        prompt += (
            "\nReturn ONLY a valid JSON object with a single key 'insight'. "
            "Do not include markdown formatting or extra text.\n"
            'Example: {"insight": "You have made great progress..."}'
        )

        insight_text = "Keep practicing to improve your readiness score."
        try:
            groq_response = _call_groq(prompt, timeout=30)
            if groq_response:
                cleaned = re.sub(r'^```(?:json)?\s*', '', groq_response.strip(), flags=re.IGNORECASE)
                cleaned = re.sub(r'\s*```$', '', cleaned)
                data = _json.loads(cleaned)
                if isinstance(data, dict) and 'insight' in data:
                    insight_text = data['insight']
        except Exception as groq_err:
            logger.warning(f"placement_readiness_api: Groq call failed: {groq_err}")
            
        readiness_data['insight'] = insight_text
        result_data = {'data_hash': data_hash, 'readiness': readiness_data}
        cache.set(cache_key, result_data, timeout=86400 * 7)
        
        return JsonResponse({
            'success': True,
            'readiness': readiness_data,
            'cached': False
        })
        
    except Exception as exc:
        import traceback as _tb
        logger.error(f"placement_readiness_api: unexpected error: {exc}\n{_tb.format_exc()}")
        return JsonResponse({
            'success': False,
            'error': 'server_error',
            'message': 'An unexpected error occurred. Please try again later.'
        }, status=500)


# ---------------------------------------------------------------------------
# Feature #21 — AI Career Mentor API endpoints
# ---------------------------------------------------------------------------

@login_required
def career_mentor_generate_api(request):
    """Feature #21 — AI Career Mentor summary generation.
    
    Returns a cached or fresh career mentor summary (summary + focus_areas + next_steps).
    Supports ?refresh=true to force regeneration.
    Gracefully returns not_enough_data when the user has insufficient signals.
    """
    import json as _json
    from django.http import JsonResponse
    from AnalysisModules.career_mentor import generate_career_mentor_summary
    import logging
    logger = logging.getLogger(__name__)

    user = request.user
    force_refresh = request.GET.get('refresh', 'false').lower() == 'true'

    try:
        result = generate_career_mentor_summary(user, refresh=force_refresh)

        if result.get('not_enough_data'):
            return JsonResponse({
                'success': False,
                'error': 'not_enough_data',
                'message': 'Complete an assessment or upload a resume to receive your personalised career mentor summary.'
            }, status=200)

        return JsonResponse({
            'success': True,
            'summary': result.get('summary', ''),
            'focus_areas': result.get('focus_areas', []),
            'next_steps': result.get('next_steps', []),
            'generated_at': result.get('generated_at', ''),
            'cached': not force_refresh and not result.get('fallback', False),
        })

    except Exception as exc:
        import traceback as _tb
        logger.error(f"career_mentor_generate_api: unexpected error: {exc}\n{_tb.format_exc()}")
        return JsonResponse({
            'success': False,
            'error': 'server_error',
            'message': 'An unexpected error occurred. Please try again later.'
        }, status=500)


@login_required
def career_mentor_chat_api(request):
    """Feature #21 — AI Career Mentor interactive chat.
    
    Takes {message, history} via POST and returns the mentor's reply.
    Not cached (conversational) but context is primed with the user's signals.
    """
    import json as _json
    from django.http import JsonResponse
    from AnalysisModules.career_mentor import career_mentor_chat
    import logging
    logger = logging.getLogger(__name__)

    user = request.user

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'method_not_allowed', 'message': 'Use POST.'}, status=405)

    try:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'invalid_json', 'message': 'Invalid JSON body.'}, status=400)

        message = body.get('message', '').strip()
        history = body.get('history') or []

        if not isinstance(history, list):
            history = []

        if not message:
            return JsonResponse({'success': False, 'error': 'empty_message', 'message': 'Please enter a message.'}, status=400)

        result = career_mentor_chat(user, message, conversation_history=history)

        return JsonResponse({
            'success': True,
            'reply': result.get('reply', ''),
        })

    except Exception as exc:
        import traceback as _tb
        logger.error(f"career_mentor_chat_api: unexpected error: {exc}\n{_tb.format_exc()}")
        return JsonResponse({
            'success': False,
            'error': 'server_error',
            'message': 'An unexpected error occurred. Please try again later.'
        }, status=500)


@login_required
def career_mentor_intake_api(request):
    """Feature #21 — Save/update the user's CareerIntake row.
    
    Accepts POST with {target_role, timeline, concern} (all optional).
    Upserts a single CareerIntake row per user.
    """
    import json as _json
    from django.http import JsonResponse
    from AnalysisAPI.models import CareerIntake
    import logging
    logger = logging.getLogger(__name__)

    user = request.user

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'method_not_allowed', 'message': 'Use POST.'}, status=405)

    try:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'invalid_json', 'message': 'Invalid JSON body.'}, status=400)

        target_role = (body.get('target_role') or '').strip()[:255] or None
        timeline = (body.get('timeline') or '').strip()[:255] or None
        concern = (body.get('concern') or '').strip() or None

        intake, created = CareerIntake.objects.update_or_create(
            user=user,
            defaults={
                'target_role': target_role,
                'timeline': timeline,
                'concern': concern,
            }
        )

        return JsonResponse({
            'success': True,
            'intake': {
                'target_role': intake.target_role,
                'timeline': intake.timeline,
                'concern': intake.concern,
                'updated_at': intake.updated_at.isoformat() if intake.updated_at else None,
            },
            'created': created,
        })

    except Exception as exc:
        import traceback as _tb
        logger.error(f"career_mentor_intake_api: unexpected error: {exc}\n{_tb.format_exc()}")
        return JsonResponse({
            'success': False,
            'error': 'server_error',
            'message': 'An unexpected error occurred. Please try again later.'
        }, status=500)

# ─── Feature #24 — Mock Placement Drive ───────────────────────────────────────

def _generate_drive_feedback(drive):
    """
    Generate a professional AI feedback summary for the mock placement drive.
    Reuses the Groq pattern from #21.
    """
    user = drive.user
    results = drive.stage_results
    
    context = f"Candidate: {user.email}\n"
    context += f"Outcome: {drive.get_final_outcome_display()}\n\n"
    
    if 'resume' in results:
        res = results['resume']
        context += f"STAGE 1: Resume Screen\n- Score: {res['score']}/100\n- Result: {'Passed' if res['passed'] else 'Eliminated'}\n"
        if drive.resume_review:
            context += f"- Feedback: {json.dumps(drive.resume_review.feedback)}\n"
            
    if 'assessment' in results:
        ast = results['assessment']
        context += f"\nSTAGE 2: Assessment\n- Score: {ast['score']}/100\n- Result: {'Passed' if ast['passed'] else 'Eliminated'}\n"
        if drive.assessment:
            context += f"- Strengths: {', '.join(drive.assessment.ai_coach_strengths or [])}\n"
            context += f"- Weaknesses: {', '.join(drive.assessment.ai_coach_weaknesses or [])}\n"
            
    if 'interview' in results:
        intv = results['interview']
        context += f"\nSTAGE 3: Interview\n- Score: {intv['score']}/100\n- Result: {'Passed' if intv['passed'] else 'Eliminated'}\n"
        if drive.interview:
            context += f"- Persona: {drive.interview.interview_mode}\n"
            context += f"- Strengths: {', '.join(drive.interview.ai_coach_strengths or [])}\n"
            context += f"- Weaknesses: {', '.join(drive.interview.ai_coach_weaknesses or [])}\n"

    prompt = (
        "You are a senior hiring manager providing final feedback to a candidate after a Mock Placement Drive. "
        "The drive consists of a Resume Screen, an Assessment, and an AI Interview. "
        "Based on the following data, write a professional, encouraging, yet honest summary of their performance. "
        "Focus on WHY they reached the stage they did and what they should focus on to secure a real offer next time. "
        "The feedback should read like a real placement feedback report, not a score dump. "
        "Keep it to 2-3 concise paragraphs.\n\n"
        f"DATA:\n{context}"
    )
    
    try:
        feedback = _call_groq(prompt, timeout=45)
        return feedback or "Feedback generation unavailable at this time."
    except Exception as e:
        logger.error(f"Failed to generate drive feedback: {e}")
        return "Feedback generation failed."

@login_required
def placement_drive_start(request):
    """Start a new Mock Placement Drive."""
    # Stage 1: Resume Screen
    latest_resume = ResumeReview.objects.filter(user=request.user).order_by('-created_at').first()
    
    if not latest_resume:
        messages.info(request, "To start a Mock Placement Drive, you must first upload your resume for screening.")
        return redirect('analysis:resume_reviewer_upload')

    # Create drive
    drive = PlacementDrive.objects.create(
        user=request.user,
        resume_review=latest_resume,
        current_stage='resume'
    )
    
    # Run Stage 1 logic
    score = latest_resume.ats_score if latest_resume.ats_score is not None else (latest_resume.overall_score * 10)
    passed = score >= 60
    
    drive.stage_results['resume'] = {
        'score': score,
        'passed': passed,
        'review_id': latest_resume.id
    }
    
    if passed:
        drive.current_stage = 'assessment'
        drive.save()
        messages.success(request, "You passed the Resume Screen! Proceeding to the Assessment stage.")
        request.session['active_placement_drive_id'] = drive.id
        return redirect('analysis:placement_drive_status')
    else:
        drive.current_stage = 'completed'
        drive.final_outcome = 'eliminated_at_resume'
        drive.completed_at = timezone.now()
        drive.ai_feedback_summary = _generate_drive_feedback(drive)
        drive.ai_feedback_cached_at = timezone.now()
        drive.save()
        return redirect('analysis:placement_drive_result', drive_id=drive.id)

@login_required
def placement_drive_status(request):
    """Dashboard for the active placement drive."""
    drive = PlacementDrive.objects.filter(user=request.user, final_outcome='in_progress').first()
    
    if not drive:
        # Check for last completed drive
        drive = PlacementDrive.objects.filter(user=request.user).order_by('-created_at').first()
        if not drive:
            return render(request, 'analysis/placement_drive_dashboard.html', {'drive': None})
        if drive.final_outcome != 'in_progress':
            return redirect('analysis:placement_drive_result', drive_id=drive.id)

    # Ensure session key is set if drive is active
    if drive:
        request.session['active_placement_drive_id'] = drive.id

    return render(request, 'analysis/placement_drive_dashboard.html', {'drive': drive})

@login_required
def placement_drive_result(request, drive_id):
    """Final result screen for a placement drive."""
    drive = get_object_or_404(PlacementDrive, id=drive_id, user=request.user)
    return render(request, 'analysis/placement_drive_result.html', {'drive': drive})

@login_required
def placement_drive_advance(request):
    """
    Orchestration hook to advance the drive stage after an assessment/interview completion.
    """
    drive_id = request.session.get('active_placement_drive_id')
    if not drive_id:
        return redirect('analysis:individual_dashboard')
        
    drive = get_object_or_404(PlacementDrive, id=drive_id, user=request.user)
    
    if drive.final_outcome != 'in_progress':
        return redirect('analysis:placement_drive_result', drive_id=drive.id)
    
    # Check what just completed
    if drive.current_stage == 'assessment':
        # Find the latest completed assessment
        latest_ast = IndividualAssessment.objects.filter(user=request.user, status='completed').order_by('-completed_at').first()
        if latest_ast and (not drive.assessment or latest_ast.id != drive.assessment.id):
            drive.assessment = latest_ast
            score = latest_ast.overall_score or 0
            passed = score >= 60
            drive.stage_results['assessment'] = {
                'score': score,
                'passed': passed,
                'assessment_id': latest_ast.id
            }
            if passed:
                drive.current_stage = 'interview'
                messages.success(request, "Great job! You passed the Assessment. Final Stage: AI Interview.")
            else:
                drive.current_stage = 'completed'
                drive.final_outcome = 'eliminated_at_assessment'
                drive.completed_at = timezone.now()
                drive.ai_feedback_summary = _generate_drive_feedback(drive)
                # Clear drive from session on failure
                if 'active_placement_drive_id' in request.session:
                    del request.session['active_placement_drive_id']
            drive.save()
            
    elif drive.current_stage == 'interview':
        # Find the latest completed interview
        latest_intv = IndividualAssessment.objects.filter(user=request.user, status='completed').order_by('-completed_at').first()
        if latest_intv and (not drive.interview or latest_intv.id != drive.interview.id):
            drive.interview = latest_intv
            score = latest_intv.overall_score or 0
            passed = score >= 70
            drive.stage_results['interview'] = {
                'score': score,
                'passed': passed,
                'assessment_id': latest_intv.id
            }
            drive.current_stage = 'completed'
            if passed:
                drive.final_outcome = 'offer'
                messages.success(request, "CONGRATULATIONS! You've received a Mock Job Offer!")
            else:
                drive.final_outcome = 'eliminated_at_interview'
            drive.completed_at = timezone.now()
            drive.ai_feedback_summary = _generate_drive_feedback(drive)
            drive.save()
            # Clear drive from session on completion
            if 'active_placement_drive_id' in request.session:
                del request.session['active_placement_drive_id']

    if drive.final_outcome != 'in_progress':
        return redirect('analysis:placement_drive_result', drive_id=drive.id)
    return redirect('analysis:placement_drive_status')
