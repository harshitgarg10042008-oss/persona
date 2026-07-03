import os
import sys

# Write all output directly to a file to avoid PowerShell swallowing it
with open("verification_results.txt", "w", encoding="utf-8") as f:
    def log(msg):
        print(msg)
        f.write(msg + "\n")

    try:
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
        django.setup()
        
        from django.test import Client
        from django.contrib.auth import get_user_model
        from AnalysisModules.AnalysisAPI.models import IndividualAssessment, PlatformJobTitle, PlatformQuestion, IndividualUser
        from UserAPI.models import CustomUser
        from django.conf import settings
        import base64
        import json
        
        client = Client()
        
        log("="*60)
        log("STEP 1: VERIFYING RATE LIMITING (Auth & Submissions)")
        log("="*60)
        
        # Test 1: Auth endpoint (Limit: 5/m)
        log("\nTesting /auth/login/ (Limit: 5/m)")
        for i in range(1, 8):
            response = client.post('/auth/login/', {'username': 'fakeuser', 'password': '123'})
            log(f"Request {i}: HTTP {response.status_code}")
        
        # Create a test user and assessment for submission testing
        User = get_user_model()
        user, created = User.objects.get_or_create(username='testuser2', defaults={'email': 'test2@test.com'})
        user.set_password('testpass123')
        user.save()
        
        ind_user, _ = IndividualUser.objects.get_or_create(user=user)
        job_title, _ = PlatformJobTitle.objects.get_or_create(title="Software Engineer")
        question, _ = PlatformQuestion.objects.get_or_create(job_title=job_title, question_text="What is your biggest weakness?")
        
        assessment, _ = IndividualAssessment.objects.get_or_create(
            user=user, 
            individual_user=ind_user,
            platform_job_title=job_title,
            status='in_progress'
        )
        
        client.login(username='testuser2', password='testpass123')
        
        # Test 2: Submission endpoint (Limit: 10/m)
        log(f"\nTesting /analysis/submit-response/{assessment.session_id}/ (Limit: 10/m)")
        url = f'/analysis/submit-response/{assessment.session_id}/'
        payload = {
            'question_id': question.id,
            'response_time': 5,
            'fullscreen_violations': 0
        }
        for i in range(1, 13):
            # No audio data first to just test rate limiting
            response = client.post(url, data=json.dumps(payload), content_type='application/json')
            log(f"Request {i}: HTTP {response.status_code}")

        
        log("\n" + "="*60)
        log("STEP 2: VERIFYING FILE UPLOAD VALIDATION")
        log("="*60)
        
        # We need a clean assessment to test uploads (we've hit limits on the previous one)
        assessment2, _ = IndividualAssessment.objects.get_or_create(
            user=user, 
            individual_user=ind_user,
            platform_job_title=job_title,
            status='pending'
        )
        
        log("\nTest A: Oversized payload (Middleware Check)")
        # 10MB limit + 1MB extra
        large_audio = "A" * (11 * 1024 * 1024) 
        payload['audio_data'] = large_audio
        url2 = f'/analysis/submit-response/{assessment2.session_id}/'
        
        response = client.post(url2, data=json.dumps(payload), content_type='application/json')
        log(f"Oversized file response: HTTP {response.status_code} - {response.content.decode('utf-8')[:100]}")
        
        log("\nTest B: Wrong-type file (PNG masquerading as Audio)")
        png_b64 = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'\x00'*10).decode('utf-8')
        payload['audio_data'] = 'data:audio/wav;base64,' + png_b64
        response = client.post(url2, data=json.dumps(payload), content_type='application/json')
        log(f"Wrong type file response: HTTP {response.status_code} - {response.content.decode('utf-8')[:100]}")
        
        log("\nTest C: Valid WAV File")
        # Need a real enough wav header or it might fail if we actually call speech analyzer
        # But speech analysis is disabled or fails gracefully if not present
        wav_b64 = base64.b64encode(b'RIFF' + b'\x00'*12).decode('utf-8')
        payload['audio_data'] = 'data:audio/wav;base64,' + wav_b64
        response = client.post(url2, data=json.dumps(payload), content_type='application/json')
        log(f"Valid WAV file response: HTTP {response.status_code} - {response.content.decode('utf-8')[:100]}")
        
    except Exception as e:
        log(f"\nEXCEPTION: {str(e)}")
        import traceback
        log(traceback.format_exc())
