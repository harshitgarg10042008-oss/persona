import os
import sys
import django
import random
from datetime import datetime, timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisModules.AnalysisAPI.models import JobRole, Assessment, AssessmentResult, AssessmentLink
from UserAPI.models import BusinessUser

def create_mock_data():
    business_user = BusinessUser.objects.first()
    if not business_user:
        print("No business user found. Aborting.")
        return

    job_role = JobRole.objects.filter(business_user=business_user).first()
    if not job_role:
        print("No job role found for business user. Creating one...")
        job_role = JobRole.objects.create(
            business_user=business_user,
            title="Senior Backend Engineer (Test Role)"
        )
        
    link, _ = AssessmentLink.objects.get_or_create(job_role=job_role)

    print(f"Creating mock candidates for role: {job_role.title}")
    
    candidates = [
        ("Alice Smith", "alice@example.com", 92.5),
        ("Bob Jones", "bob@example.com", 85.0),
        ("Charlie Brown", "charlie@example.com", 78.5),
        ("Diana Prince", "diana@example.com", 96.0)
    ]
    
    for idx, (name, email, score) in enumerate(candidates):
        assessment = Assessment.objects.create(
            assessment_type='business',
            assessment_link=link,
            candidate_name=name,
            candidate_email=email,
            status='completed',
            job_title=job_role.title,
            completed_at=timezone.now() - timedelta(days=idx)
        )
        
        AssessmentResult.objects.create(
            assessment=assessment,
            overall_score=score,
            confidence_score=random.uniform(70, 98),
            posture_score=random.uniform(60, 95),
            attire_appropriateness=random.choice(['excellent', 'good', 'fair']),
            speech_pace=random.uniform(3, 6)
        )
        print(f"Created candidate: {name} - Score: {score}")

if __name__ == "__main__":
    create_mock_data()
