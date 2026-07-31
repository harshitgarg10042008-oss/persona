import os
import json
from AnalysisModules.feedback_generator import generate_job_matches
from AnalysisModules.AnalysisAPI.models import PlatformJobTitle

def run_tests():
    output = []
    output.append("Starting tests...")
    
    jobs = list(PlatformJobTitle.objects.filter(is_active=True).values_list('title', flat=True))
    if not jobs:
        jobs = ["Software Engineer", "Data Scientist", "Product Manager", "Marketing Manager", "HR Generalist"]
        
    # Test 1: Full Data
    context1 = "Candidate has 5 years of Python/Django experience. Strong communication skills. Recent assessment score: 90/100 for Software Engineer. Weakness: occasional stutters."
    matches1 = generate_job_matches(context1, jobs)
    output.append(f"\n--- Test 1 (Full Data) ---\nContext: {context1}\nResult: {json.dumps(matches1, indent=2)}")
    
    # Test 2: Partial Data
    context2 = "Recent grad with interest in data and analytics. No formal experience yet. Resume review score: 60/100."
    matches2 = generate_job_matches(context2, jobs)
    output.append(f"\n--- Test 2 (Partial Data) ---\nContext: {context2}\nResult: {json.dumps(matches2, indent=2)}")
    
    # Test 3: Minimal Data
    context3 = "Has good communication skills but no technical background."
    matches3 = generate_job_matches(context3, jobs)
    output.append(f"\n--- Test 3 (Minimal Data) ---\nContext: {context3}\nResult: {json.dumps(matches3, indent=2)}")
    
    with open('c:/Users/vishe/OneDrive/Desktop/Goal/persona/test_output.txt', 'w') as f:
        f.write("\n".join(output))

try:
    if not os.path.exists('c:/Users/vishe/OneDrive/Desktop/Goal/persona/test_output.txt'):
        import threading
        t = threading.Thread(target=run_tests)
        t.start()
except Exception as e:
    with open('c:/Users/vishe/OneDrive/Desktop/Goal/persona/test_output.txt', 'w') as f:
        f.write(f"Error: {e}")
