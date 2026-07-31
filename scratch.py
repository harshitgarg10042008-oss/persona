import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisModules.feedback_generator import _call_groq
from AnalysisModules.AnalysisAPI.models import PlatformJobTitle, IndividualAssessment, ResumeReview
from UserAPI.models import CustomUser

print("Testing _call_groq...")
response = _call_groq("Say 'Groq is working' if you can read this.", timeout=10)
print(f"Groq Response: {response}")

print("\n--- DB Data ---")
users = CustomUser.objects.all()[:3]
for u in users:
    print(f"User: {u.email}")
    resumes = ResumeReview.objects.filter(user=u).order_by('-created_at')
    print(f"  Resumes: {resumes.count()}")
    if resumes.exists():
        print(f"  Latest resume score: {resumes.first().overall_score}")
    
    assessments = IndividualAssessment.objects.filter(user=u, status='completed')
    print(f"  Completed Assessments: {assessments.count()}")
    if assessments.exists():
        a = assessments.first()
        print(f"  Latest assessment: {a.platform_job_title.title} - Score: {a.overall_score}")

jobs = PlatformJobTitle.objects.filter(is_active=True)
print(f"\nActive Platform Job Titles: {jobs.count()}")
for j in jobs[:5]:
    print(f" - {j.title} ({j.category})")
