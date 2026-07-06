import os
import sys
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisModules.AnalysisAPI.models import IndividualAssessment, AssessmentResponse

print("Looking for completed assessments with speech analysis...")
assessments = IndividualAssessment.objects.exclude(completed_at=None)
for a in assessments:
    responses = a.responses.all()
    has_speech = False
    for r in responses:
        if isinstance(r.analysis_data, dict):
            if 'speech_analysis' in r.analysis_data:
                has_speech = True
                break
    if has_speech:
        print(f"Found Assessment: {a.session_id} - Questions: {responses.count()}")
        for r in responses:
            sa = r.analysis_data.get('speech_analysis', {}) if isinstance(r.analysis_data, dict) else {}
            audio_features = sa.get('details', {}).get('audio_features', {})
            print(f"  Q{r.question_order}:")
            print(f"    avg_energy: {audio_features.get('avg_energy')}")
            print(f"    speaking_rate: {sa.get('speaking_rate')}")
            print(f"    pitch_variance: {audio_features.get('pitch_variance')}")
        print("---")
