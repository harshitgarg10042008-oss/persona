from django.test import SimpleTestCase, override_settings

from AnalysisModules.feedback_generator import (
    evaluate_answer_content,
    generate_feedback_summary,
)


class FeedbackGeneratorTests(SimpleTestCase):
    @override_settings(GROQ_API_KEY=None)
    def test_evaluate_answer_content_falls_back_without_api_key(self):
        result = evaluate_answer_content(
            question_text="Tell me about a time you solved a problem.",
            transcript="I solved a problem by planning carefully and coordinating with my team.",
        )

        self.assertIsNone(result['content_correctness_score'])
        self.assertIn('unavailable', result['explanation'].lower())

    @override_settings(GROQ_API_KEY=None)
    def test_generate_feedback_summary_falls_back_without_evaluations(self):
        summary = generate_feedback_summary(
            {
                'overall_score': 8.2,
                'body_language_score': 7.5,
                'attire_score': 8.0,
                'speaking_score': 7.8,
            },
            [],
        )

        self.assertTrue(summary)
        self.assertIn('feedback', summary.lower())


from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from AnalysisAPI.models import PlatformJobTitle, IndividualAssessment, IndividualAssessmentResponse, PlatformQuestion
from UserAPI.models import BusinessUser, IndividualUser

User = get_user_model()

class AssessmentViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpassword123')
        self.job_title = PlatformJobTitle.objects.create(title='Test Job', category='technology')
        self.assessment = IndividualAssessment.objects.create(
            user=self.user,
            platform_job_title=self.job_title,
            status='in_progress'
        )
        self.question = PlatformQuestion.objects.create(
            job_title=self.job_title,
            question_text="Test question"
        )
        self.client.login(username='testuser', password='testpassword123')

    def test_complete_individual_assessment_no_fallback_score(self):
        """
        Test that when analysis data is missing/None, complete_individual_assessment
        does not assign a fake fallback score.
        """
        # Create a response with empty analysis_data
        IndividualAssessmentResponse.objects.create(
            assessment=self.assessment,
            question=self.question,
            question_order=1,
            analysis_data={}
        )
        
        # Complete assessment
        url = reverse('analysis:complete_individual_assessment', args=[self.assessment.session_id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.status, 'completed')
        self.assertIsNone(self.assessment.overall_score)
        self.assertIsNone(self.assessment.speaking_score)
        
    def test_complete_individual_assessment_pending_speech(self):
        """
        Test that complete_individual_assessment does not mark assessment complete
        while a response's speech_analysis_status is still 'pending'.
        """
        IndividualAssessmentResponse.objects.create(
            assessment=self.assessment,
            question=self.question,
            question_order=1,
            analysis_data={'speech_analysis_status': 'pending'}
        )
        
        url = reverse('analysis:complete_individual_assessment', args=[self.assessment.session_id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # Should render processing_results.html
        self.assertTemplateUsed(response, 'analysis/processing_results.html')
        
        # Assessment should NOT be marked complete
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.status, 'in_progress')


class CSRFTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpassword123')
        self.job_title = PlatformJobTitle.objects.create(title='Test Job', category='technology')
        self.assessment = IndividualAssessment.objects.create(
            user=self.user,
            platform_job_title=self.job_title,
            status='in_progress'
        )

    def test_submit_response_csrf_enforced(self):
        """
        Test that submitting a response without a CSRF token is rejected (403).
        """
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(username='testuser', password='testpassword123')
        
        url = reverse('analysis:submit_assessment_response', args=[self.assessment.session_id])
        # Post without CSRF token
        response = csrf_client.post(url, {'response_text': 'test'})
        
        self.assertEqual(response.status_code, 403)

