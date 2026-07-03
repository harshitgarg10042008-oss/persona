import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
import django; django.setup()

from AnalysisModules.AnalysisAPI.models import IndividualAssessment
import json

assessment = IndividualAssessment.objects.filter(status='completed', overall_score__isnull=False).order_by('-completed_at').first()

if assessment:
    print("Assessment ID:", assessment.id)
    if hasattr(assessment, 'improvement_roadmap'):
        print("Roadmap:")
        print(json.dumps(assessment.improvement_roadmap, indent=2))
    else:
        print("No improvement_roadmap attribute found.")
else:
    print("No assessment found.")
