import json
from AnalysisModules.feedback_generator import generate_job_matches
from AnalysisAPI.models import PlatformJobTitle

jobs = list(PlatformJobTitle.objects.filter(is_active=True).values_list('title', flat=True))

# Test 1: Full Data
context1 = "Candidate has 5 years of Python/Django experience. Strong communication skills. Recent assessment score: 90/100 for Software Engineer. Weakness: occasional stutters."
matches1 = generate_job_matches(context1, jobs)
print("\n--- Test 1 (Full Data) ---")
print(json.dumps(matches1, indent=2))

# Test 2: Partial Data
context2 = "Recent grad with interest in data and analytics. No formal experience yet. Resume review score: 60/100."
matches2 = generate_job_matches(context2, jobs)
print("\n--- Test 2 (Partial Data) ---")
print(json.dumps(matches2, indent=2))

# Test 3: Minimal Data
context3 = "Has good communication skills but no technical background."
matches3 = generate_job_matches(context3, jobs)
print("\n--- Test 3 (Minimal Data) ---")
print(json.dumps(matches3, indent=2))
