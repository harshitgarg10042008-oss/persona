import os
import sys
import json
import subprocess

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Verify the latest completed assessment roadmap using real data only.'

    def handle(self, *args, **options):
        print("=" * 60)
        print("1. Running Migrations")
        print("=" * 60)
        try:
            print("Running makemigrations AnalysisAPI...")
            subprocess.run([sys.executable, 'manage.py', 'makemigrations', 'AnalysisAPI'])
            print("\nRunning migrate...")
            subprocess.run([sys.executable, 'manage.py', 'migrate'])
        except Exception as e:
            print(f"Migration error: {e}")

        print("\n" + "=" * 60)
        print("2 & 3. Fetching Real Assessment & Running Roadmap")
        print("=" * 60)

        from AnalysisAPI.models import IndividualAssessment
        from AnalysisModules.feedback_generator import generate_improvement_roadmap

        # Pick the latest completed assessment that actually has scores
        assessment = IndividualAssessment.objects.filter(
            status='completed',
            overall_score__isnull=False
        ).order_by('-completed_at').first()

        if not assessment:
            print("No completed assessments with scores found in DB!")
            return

        print(f"Selected Assessment ID: {assessment.id}")
        print(f"Overall Score: {assessment.overall_score}")
        print(f"Speaking Score: {assessment.speaking_score}")
        print(f"Body Language Score: {assessment.body_language_score}")
        print(f"Attire Score: {assessment.attire_score}")

        # Fetch real speech details (filler words etc)
        speech_details = {}
        first_resp = assessment.responses.order_by('question_order').first()
        if first_resp and isinstance(first_resp.analysis_data, dict):
            speech_details = first_resp.analysis_data.get('speech_analysis', {})

        fluency = speech_details.get('details', {}).get('fluency', {})
        print(f"\nReal Fluency Data from DB:")
        print(json.dumps(fluency, indent=2))

        scores = {
            'overall_score': assessment.overall_score,
            'body_language_score': assessment.body_language_score,
            'attire_score': assessment.attire_score,
            'speaking_score': assessment.speaking_score,
        }

        print("\nCalling generate_improvement_roadmap()...")
        real_roadmap = generate_improvement_roadmap(scores, speech_details)

        print("\n" + "=" * 60)
        print("4 & 5. ACTUAL RAW JSON RETURNED BY GROQ")
        print("=" * 60)
        print(json.dumps(real_roadmap, indent=2))

        # Validation checks
        print("\nValidating output...")
        roadmap_str = json.dumps(real_roadmap).lower()
        has_eye_contact = "eye" in roadmap_str or "gaze" in roadmap_str
        print(f"- Mentions 'eye' or 'gaze': {'YES (Failed)' if has_eye_contact else 'NO (Passed)'}")

        print("\n" + "=" * 60)
        print("6. Testing Missing Data Case (None Scores)")
        print("=" * 60)
        missing_scores = {
            'overall_score': None,
            'body_language_score': None,
            'attire_score': None,
            'speaking_score': None,
        }
        fallback_roadmap = generate_improvement_roadmap(missing_scores, {})
        print(f"Result with missing data: {fallback_roadmap}")
        print("Expected: None (so 'Analysis unavailable' renders in UI)")

        print("\nDone! Please view this assessment in the browser to confirm UI (Step 7).")
