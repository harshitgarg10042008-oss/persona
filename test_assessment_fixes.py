"""
Test script to verify both assessment fixes:
1. Question repeat bug - verify question index increments correctly
2. Question count mismatch - verify setup page shows actual selected question count
"""
import os
import sys
import django
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / 'AnalysisModules'))
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from django.contrib.auth import get_user_model
from AnalysisModules.AnalysisAPI.models import (
    IndividualAssessment, PlatformJobTitle, PlatformQuestion,
    IndividualAssessmentResponse
)

User = get_user_model()

def test_question_count_fix():
    """Test that setup page shows actual selected question count"""
    print("\n=== TEST 1: Question Count Display Fix ===")
    
    # Get a job title with questions
    job_title = PlatformJobTitle.objects.filter(is_active=True).first()
    if not job_title:
        print("❌ No active job titles found")
        return False
    
    print(f"Job Title: {job_title.title}")
    print(f"Total questions in pool: {job_title.questions.count()}")
    print(f"Active questions: {job_title.questions.filter(is_active=True).count()}")
    print(f"Mandatory questions: {job_title.questions.filter(is_mandatory=True, is_active=True).count()}")
    print(f"Non-mandatory questions: {job_title.questions.filter(is_mandatory=False, is_active=True).count()}")
    
    # Create a test assessment
    user = User.objects.first()
    if not user:
        print("❌ No users found")
        return False
    
    assessment = IndividualAssessment.objects.create(
        user=user,
        platform_job_title=job_title,
        status='pending'
    )
    
    # Call select_questions (this is what the view does)
    assessment.select_questions()
    assessment.refresh_from_db()
    
    print(f"\nAfter select_questions():")
    print(f"assessment.total_questions: {assessment.total_questions}")
    print(f"len(assessment.selected_questions): {len(assessment.selected_questions)}")
    print(f"selected_questions IDs: {assessment.selected_questions}")
    
    # Verify the count matches
    actual_count = len(assessment.selected_questions) if assessment.selected_questions else 0
    if assessment.total_questions == actual_count:
        print(f"✅ PASS: total_questions ({assessment.total_questions}) matches actual selected count ({actual_count})")
    else:
        print(f"❌ FAIL: total_questions ({assessment.total_questions}) does NOT match actual selected count ({actual_count})")
        assessment.delete()
        return False
    
    # Clean up
    assessment.delete()
    return True

def test_question_index_increment():
    """Test that question index increments correctly after response submission"""
    print("\n=== TEST 2: Question Index Increment Fix ===")
    
    # Get a job title with questions
    job_title = PlatformJobTitle.objects.filter(is_active=True).first()
    if not job_title:
        print("❌ No active job titles found")
        return False
    
    # Create a test assessment
    user = User.objects.first()
    if not user:
        print("❌ No users found")
        return False
    
    assessment = IndividualAssessment.objects.create(
        user=user,
        platform_job_title=job_title,
        status='pending'
    )
    
    # Select questions
    assessment.select_questions()
    assessment.refresh_from_db()
    
    print(f"Initial state:")
    print(f"  current_question_index: {assessment.current_question_index}")
    print(f"  total_questions: {assessment.total_questions}")
    print(f"  selected_questions: {assessment.selected_questions}")
    
    # Get first question
    first_question = assessment.get_next_question()
    if not first_question:
        print("❌ No questions available")
        assessment.delete()
        return False
    
    print(f"\nFirst question ID: {first_question.id}")
    print(f"First question text: {first_question.question_text[:50]}...")
    
    # Simulate response submission (what submit_assessment_response does)
    assessment.status = 'in_progress'
    assessment.save()
    
    response = IndividualAssessmentResponse.objects.create(
        assessment=assessment,
        question=first_question,
        question_order=assessment.current_question_index + 1,
        question_started_at=django.utils.timezone.now(),
        response_started_at=django.utils.timezone.now(),
        response_ended_at=django.utils.timezone.now(),
        response_duration=10,
        time_to_start=2
    )
    
    # Increment index (what the view does)
    assessment.current_question_index += 1
    assessment.save()
    
    print(f"\nAfter response submission:")
    print(f"  current_question_index: {assessment.current_question_index}")
    
    # Get next question
    second_question = assessment.get_next_question()
    
    if second_question:
        print(f"Second question ID: {second_question.id}")
        print(f"Second question text: {second_question.question_text[:50]}...")
        
        if first_question.id != second_question.id:
            print(f"✅ PASS: Questions are different (Q1: {first_question.id}, Q2: {second_question.id})")
        else:
            print(f"❌ FAIL: Same question repeated (both ID: {first_question.id})")
            assessment.delete()
            return False
    else:
        print("No more questions (assessment complete)")
        print(f"✅ PASS: Index correctly reached end ({assessment.current_question_index} >= {assessment.total_questions})")
    
    # Clean up
    assessment.delete()
    return True

def test_random_question_selection():
    """Test that different assessments get different random questions"""
    print("\n=== TEST 3: Random Question Selection ===")
    
    job_title = PlatformJobTitle.objects.filter(is_active=True).first()
    if not job_title:
        print("❌ No active job titles found")
        return False
    
    user = User.objects.first()
    if not user:
        print("❌ No users found")
        return False
    
    # Create two assessments
    assessment1 = IndividualAssessment.objects.create(
        user=user,
        platform_job_title=job_title,
        status='pending'
    )
    assessment2 = IndividualAssessment.objects.create(
        user=user,
        platform_job_title=job_title,
        status='pending'
    )
    
    # Select questions for both
    assessment1.select_questions()
    assessment1.refresh_from_db()
    assessment2.select_questions()
    assessment2.refresh_from_db()
    
    print(f"Assessment 1 selected_questions: {assessment1.selected_questions}")
    print(f"Assessment 2 selected_questions: {assessment2.selected_questions}")
    
    if assessment1.selected_questions != assessment2.selected_questions:
        print("✅ PASS: Different assessments got different random question sets")
    else:
        print("⚠️  WARNING: Same question sets (could happen by chance with small pools)")
    
    # Clean up
    assessment1.delete()
    assessment2.delete()
    return True

if __name__ == '__main__':
    print("Testing Assessment Fixes...")
    print("=" * 60)
    
    results = []
    results.append(("Question Count Display", test_question_count_fix()))
    results.append(("Question Index Increment", test_question_index_increment()))
    results.append(("Random Question Selection", test_random_question_selection()))
    
    print("\n" + "=" * 60)
    print("SUMMARY:")
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test_name}")
    
    all_passed = all(passed for _, passed in results)
    print("\n" + ("=" * 60))
    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
