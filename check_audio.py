import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisAPI.models import IndividualAssessment

try:
    assessment = IndividualAssessment.objects.order_by('-started_at').first()
    responses = assessment.responses.all()
    for r in responses:
        if r.audio_file:
            print(f"Response Q{r.question_order}:")
            print(f"  Audio Path: {r.audio_file.path}")
            print(f"  File Exists: {os.path.exists(r.audio_file.path)}")
            if os.path.exists(r.audio_file.path):
                print(f"  File Size: {os.path.getsize(r.audio_file.path)} bytes")
        else:
            print(f"Response Q{r.question_order} has no audio_file associated.")
except Exception as e:
    print(f"Error: {e}")
