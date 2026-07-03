import os, sys, json
sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
import django; django.setup()

from AnalysisModules.AnalysisAPI.models import IndividualAssessment
from AnalysisModules.feedback_generator import generate_improvement_roadmap

# Find the latest completed assessment with scores
assessment = IndividualAssessment.objects.filter(status='completed', overall_score__isnull=False).order_by('-completed_at').first()

if not assessment:
    print("No completed assessment found.")
    sys.exit(0)

with open('verify_output.txt', 'w', encoding='utf-8') as out_f:
    def _print(msg):
        out_f.write(str(msg) + '\n')
        print(msg)

    _print(f"Testing roadmap generation for assessment {assessment.id} (Score: {assessment.overall_score})")

    # Extract speech details
    speech_details = {}
    responses = assessment.responses.all().order_by('question_order')
    if responses.exists():
        first_resp_data = responses.first().analysis_data
        if isinstance(first_resp_data, dict):
            speech_details = first_resp_data.get('speech_analysis', {})

    scores = {
        'overall_score': assessment.overall_score,
        'body_language_score': assessment.body_language_score,
        'attire_score': assessment.attire_score,
        'speaking_score': assessment.speaking_score,
    }

    _print("\n--- Input Scores ---")
    _print(json.dumps(scores, indent=2))

    _print("\n--- Input Speech Details ---")
    _print(json.dumps(speech_details.get('details', {}).get('fluency', {}), indent=2))

    # Generate Roadmap
    _print("\nGenerating roadmap via Groq...")
    roadmap = generate_improvement_roadmap(scores, speech_details)

    _print("\n--- Generated Roadmap JSON Output ---")
    _print(json.dumps(roadmap, indent=2))

    if roadmap:
        # Save it to confirm the model field works (if migrated)
        try:
            assessment.improvement_roadmap = roadmap
            assessment.save(update_fields=['improvement_roadmap'])
            _print("\nSuccessfully saved to database!")
        except Exception as e:
            _print(f"\nFailed to save to database (migration issue?): {str(e)}")
