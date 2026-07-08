import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'persona.settings')
django.setup()

from AnalysisModules.models import IndividualAssessment

qs = IndividualAssessment.objects.all().order_by('-created_at')[:5]

with open('db_dump.txt', 'w') as f:
    for a in qs:
        f.write(f"ID: {a.id} | Role: {a.platform_job_title.title} | Status: {a.status} | Overall Score: {a.overall_score} | Started At: {a.started_at} | Completed At: {a.completed_at}\n")
