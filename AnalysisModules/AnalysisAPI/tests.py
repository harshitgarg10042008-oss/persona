from django.test import SimpleTestCase, override_settings

from AnalysisModules.feedback_generator import (
    evaluate_answer_content,
    generate_feedback_summary,
)


class FeedbackGeneratorTests(SimpleTestCase):
    @override_settings(GEMINI_API_KEY=None)
    def test_evaluate_answer_content_falls_back_without_api_key(self):
        result = evaluate_answer_content(
            question_text="Tell me about a time you solved a problem.",
            transcript="I solved a problem by planning carefully and coordinating with my team.",
        )

        self.assertIsNone(result['content_correctness_score'])
        self.assertIn('unavailable', result['explanation'].lower())

    @override_settings(GEMINI_API_KEY=None)
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
