from AnalysisModules.AnalysisAPI.models import IndividualAssessment, PlatformJobTitle, PlatformQuestion, IndividualAssessmentResponse
from django.contrib.auth import get_user_model
import django.utils.timezone

User = get_user_model()

# Test 1: Question count display
print('=== TEST 1: Question Count Display ===')
job_title = PlatformJobTitle.objects.filter(is_active=True).first()
print(f'Job Title: {job_title.title}')
print(f'Total pool: {job_title.questions.count()}')
print(f'Active: {job_title.questions.filter(is_active=True).count()}')
print(f'Mandatory: {job_title.questions.filter(is_mandatory=True, is_active=True).count()}')

user = User.objects.first()
assessment = IndividualAssessment.objects.create(user=user, platform_job_title=job_title, status='pending')
assessment.select_questions()
assessment.refresh_from_db()
print(f'After select_questions():')
print(f'  total_questions: {assessment.total_questions}')
print(f'  len(selected_questions): {len(assessment.selected_questions)}')
actual = len(assessment.selected_questions) if assessment.selected_questions else 0
if assessment.total_questions == actual:
    print('✅ PASS: Counts match')
else:
    print(f'❌ FAIL: Mismatch ({assessment.total_questions} vs {actual})')

# Test 2: Question index increment
print('\n=== TEST 2: Question Index Increment ===')
print(f'Initial current_question_index: {assessment.current_question_index}')
first_q = assessment.get_next_question()
print(f'First question ID: {first_q.id if first_q else None}')

assessment.status = 'in_progress'
assessment.save()
IndividualAssessmentResponse.objects.create(
    assessment=assessment, question=first_q, question_order=assessment.current_question_index + 1,
    question_started_at=django.utils.timezone.now(), response_started_at=django.utils.timezone.now(),
    response_ended_at=django.utils.timezone.now(), response_duration=10, time_to_start=2
)
assessment.current_question_index += 1
assessment.save()
print(f'After submission: current_question_index = {assessment.current_question_index}')

second_q = assessment.get_next_question()
if second_q and first_q.id != second_q.id:
    print(f'✅ PASS: Different questions (Q1: {first_q.id}, Q2: {second_q.id})')
elif second_q:
    print(f'❌ FAIL: Same question (both ID: {first_q.id})')
else:
    print('✅ PASS: Assessment complete')

assessment.delete()
print('\nTests completed')
