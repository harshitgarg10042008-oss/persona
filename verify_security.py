import os
import sys
import traceback

log_file = open("security_log.txt", "w")
sys.stdout = log_file
sys.stderr = log_file

try:
    import django
    from django.conf import settings
    from django.test import Client
    
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
    django.setup()
    
    client = Client()
    
    print("="*60)
    print("1. Testing Rate Limits on Login Endpoint")
    print("="*60)
    for i in range(7):
        response = client.post('/auth/login/', {'username': 'test', 'password': '123'})
        print(f"Request {i+1}: HTTP {response.status_code}")
    
    print("\n" + "="*60)
    print("2. Testing Security Headers")
    print("="*60)
    response = client.get('/auth/login/')
    headers_to_check = ['X-Content-Type-Options', 'X-Frame-Options', 'Referrer-Policy', 'Permissions-Policy', 'Content-Security-Policy']
    for h in headers_to_check:
        print(f"{h}: {response.headers.get(h, 'MISSING')}")
    
    print("\n" + "="*60)
    print("3. Testing Request Size Limits")
    print("="*60)
    large_payload = "A" * (getattr(settings, 'MAX_AUDIO_MB', 10) * 1024 * 1024 + 10)
    response = client.post(
        '/analysis/individual/00000000-0000-0000-0000-000000000000/submit/',
        data=large_payload,
        content_type='application/json',
        CONTENT_LENGTH=len(large_payload)
    )
    print(f"Large Payload Request: HTTP {response.status_code} - {response.content}")
    
    print("\n" + "="*60)
    print("4. Testing Upload Validators")
    print("="*60)
    from AnalysisModules.AnalysisAPI.upload_validators import validate_audio_b64, validate_image_b64
    import base64
    
    valid_wav = base64.b64encode(b'RIFF' + b'\x00'*12).decode('utf-8')
    print(f"Valid WAV: {validate_audio_b64(valid_wav)}")
    
    invalid_audio = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'\x00'*8).decode('utf-8')
    print(f"Invalid Audio (PNG): {validate_audio_b64(invalid_audio)}")
    
    valid_jpg = base64.b64encode(b'\xff\xd8\xff' + b'\x00'*13).decode('utf-8')
    print(f"Valid JPEG: {validate_image_b64(valid_jpg)}")
    
    invalid_image = base64.b64encode(b'RIFF' + b'\x00'*4 + b'WAVE' + b'\x00'*4).decode('utf-8')
    print(f"Invalid Image (WAV): {validate_image_b64(invalid_image)}")

except Exception as e:
    print("EXCEPTION OCCURRED:")
    traceback.print_exc()

finally:
    log_file.close()
