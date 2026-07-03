import os
import django
import base64
import json

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from AnalysisAPI.models import IndividualAssessment, PlatformJobTitle, PlatformQuestion
from django.conf import settings

User = get_user_model()
client = Client(HTTP_HOST='localhost')

print("=" * 60)
print("STEP 1: VERIFYING RATE LIMITING")
print("=" * 60)

# Test login rate limit (5/min)
print("\n[+] Hitting /auth/login/ 6 times (Limit is 5/min)...")
for i in range(1, 7):
    response = client.post('/auth/login/', {'username': 'test', 'password': '123'})
    print(f"Request {i}: HTTP {response.status_code}")

print("\n" + "=" * 60)
print("STEP 2: VERIFYING FILE UPLOAD VALIDATION")
print("=" * 60)

# Setup user and a fresh assessment for each upload test
user, _ = User.objects.get_or_create(
    username='testuser_upload',
    defaults={'email': 'upload_test@test.com'},
)
job_title, _ = PlatformJobTitle.objects.get_or_create(title="Tester")
question, _ = PlatformQuestion.objects.get_or_create(
    job_title=job_title,
    question_text="Upload validation test question",
)

# Fresh assessment per run so we never hit "already submitted"
assessment = IndividualAssessment.objects.create(
    user=user,
    platform_job_title=job_title,
    status='in_progress',
)

url = f'/analysis/combined-response/{assessment.session_id}/'
base_payload = {
    'question_id': question.id,
    'response_time': 5,
    'fullscreen_violations': 0,
}

print(f"\n[+] Testing Oversized File Rejection (Limit: {settings.MAX_AUDIO_MB}MB)...")
large_payload = dict(base_payload)
large_audio = 'data:audio/wav;base64,' + ('A' * (settings.MAX_AUDIO_MB * 1024 * 1024 + 10))
large_payload['audio_data'] = large_audio
response = client.post(
    url,
    data=json.dumps(large_payload),
    content_type='application/json',
)
print(f"Response: HTTP {response.status_code} - {response.content.decode('utf-8')[:200]}")

print("\n[+] Testing Invalid File Type (PNG disguised as Audio)...")
# New assessment — oversized test is rejected by middleware before creating a response
assessment2 = IndividualAssessment.objects.create(
    user=user,
    platform_job_title=job_title,
    status='in_progress',
)
url2 = f'/analysis/combined-response/{assessment2.session_id}/'
png_b64 = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'\x00' * 10).decode('utf-8')
invalid_payload = dict(base_payload)
invalid_payload['audio_data'] = 'data:audio/wav;base64,' + png_b64
response = client.post(
    url2,
    data=json.dumps(invalid_payload),
    content_type='application/json',
)
print(f"Response: HTTP {response.status_code} - {response.content.decode('utf-8')[:200]}")

print("\n" + "=" * 60)
print("STEP 3: VERIFYING PASSWORD RESET FLOW")
print("=" * 60)

print("\n[+] Triggering Password Reset for 'test@test.com'...")
print("[+] Using console email backend — reset link will appear in output below:")
response = client.post('/auth/password_reset/', {'email': 'test@test.com'})
print(f"Reset Request Response: HTTP {response.status_code}")
if response.status_code == 302:
    print("[+] Password reset request succeeded.")
else:
    print(f"[-] Unexpected response: {response.content.decode('utf-8')[:200]}")
