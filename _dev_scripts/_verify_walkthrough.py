"""Full E2E walkthrough: signup -> assessment -> processing -> results."""
import base64
import json
import os
import sys
import time
import re
import uuid

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')

import django
django.setup()

from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from AnalysisAPI.models import (
    IndividualAssessment,
    PlatformJobTitle,
    PlatformQuestion,
)

User = get_user_model()

TINY_JPEG_B64 = (
    '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof'
    'Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwh'
    'MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAAR'
    'CAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAA'
    'AAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMB'
    'AAIRAxEAPwCwAA8A/9k='
)

SAMPLE_AUDIO_PATH = os.path.join(os.path.dirname(__file__), 'verify_speech.webm')
GEMINI_FALLBACK_SNIPPET = 'Feedback summary is currently unavailable'


def fail(msg):
    print(f'FAIL: {msg}')
    sys.exit(1)


def ok(msg):
    print(f'OK: {msg}')


def extract_csrf(html):
    m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
    return m.group(1) if m else None


def main():
    if not os.path.exists(SAMPLE_AUDIO_PATH):
        fail(f'Missing audio sample: {SAMPLE_AUDIO_PATH}')

    with open(SAMPLE_AUDIO_PATH, 'rb') as f:
        audio_bytes = f.read()
    if len(audio_bytes) < 10000:
        fail(f'Audio sample too small: {len(audio_bytes)} bytes')
    audio_b64 = base64.b64encode(audio_bytes).decode('ascii')
    ok(f'Audio sample: {len(audio_bytes)} bytes')

    suffix = uuid.uuid4().hex[:8]
    email = f'e2e_verify_{suffix}@example.com'
    password = 'TestPass123!'

    job_title = PlatformJobTitle.objects.filter(is_active=True, id=4).first()
    if not job_title:
        job_title = PlatformJobTitle.objects.filter(is_active=True).first()
    if not job_title:
        fail('No active PlatformJobTitle in database')

    questions = list(job_title.questions.filter(is_active=True).order_by('id'))
    if not questions:
        fail(f'No questions for job title {job_title.title}')

    with override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1']):
        client = Client(enforce_csrf_checks=True)

        # Sign up (GET form first for CSRF cookie)
        signup_page = client.get('/auth/signup/')
        csrf_form = extract_csrf(signup_page.content.decode('utf-8', errors='replace'))
        signup_resp = client.post('/auth/signup/', {
            'user_type': 'individual',
            'name': f'E2E User {suffix}',
            'email': email,
            'password1': password,
            'password2': password,
            'csrfmiddlewaretoken': csrf_form,
        })
        if signup_resp.status_code not in (200, 302):
            fail(f'Signup returned {signup_resp.status_code}')

        user = User.objects.filter(email=email).first()
        if not user:
            fail('User not created after signup')
        ok(f'Signed up user {email}')

        if not client.login(username=email, password=password):
            client.force_login(user)
        ok('Logged in')

        # Start assessment (Data Analyst = 5 questions)
        dash = client.get('/analysis/individual/')
        csrf_form = extract_csrf(dash.content.decode('utf-8', errors='replace'))
        start_resp = client.post('/analysis/individual/start/', {
            'job_title_id': str(job_title.id),
            'csrfmiddlewaretoken': csrf_form,
        })
        if start_resp.status_code != 302:
            fail(f'Start assessment returned {start_resp.status_code}')

        assessment = IndividualAssessment.objects.filter(user=user).order_by('-created_at').first()
        if not assessment:
            fail('Assessment not created after start')
        session_id = str(assessment.session_id)
        ok(f'Started assessment session_id={session_id}')

        page_url = f'/analysis/assessment/{session_id}/combined/'
        page = client.get(page_url)
        if page.status_code != 200:
            fail(f'GET combined assessment returned {page.status_code}')
        csrf_cookie = client.cookies.get('csrftoken')
        if not csrf_cookie:
            fail('No csrftoken cookie')
        csrf_token = csrf_cookie.value
        ok('Combined assessment page loaded with CSRF token')

        snapshot_url = f'/analysis/combined-snapshot/{session_id}/'
        response_url = f'/analysis/combined-response/{session_id}/'

        for i, question in enumerate(questions, 1):
            snap_body = json.dumps({
                'image_data': f'data:image/jpeg;base64,{TINY_JPEG_B64}',
                'analysis_type': 'body_language' if i % 2 else 'attire',
                'question_id': question.id,
            })
            snap_resp = client.post(
                snapshot_url,
                data=snap_body,
                content_type='application/json',
                HTTP_X_CSRFTOKEN=csrf_token,
            )
            if snap_resp.status_code != 200 or not snap_resp.json().get('success'):
                fail(f'Q{i} snapshot failed: {snap_resp.status_code} {snap_resp.content[:200]}')

            audio_body = json.dumps({
                'question_id': question.id,
                'audio_data': audio_b64,
                'response_time': 5,
                'fullscreen_violations': 0,
            })
            audio_resp = client.post(
                response_url,
                data=audio_body,
                content_type='application/json',
                HTTP_X_CSRFTOKEN=csrf_token,
            )
            if audio_resp.status_code != 200:
                fail(f'Q{i} audio CSRF/status error: {audio_resp.status_code}')
            audio_data = audio_resp.json()
            if not audio_data.get('success'):
                fail(f'Q{i} audio submission failed: {audio_data}')

        ok(f'Submitted {len(questions)} questions with snapshots + audio')

        # Poll processing status (mirrors processing_results.html)
        status_url = f'/analysis/processing-status/{session_id}/'
        complete_url = f'/analysis/individual/{session_id}/complete/'
        deadline = time.time() + 300
        processing_done = False

        while time.time() < deadline:
            status_resp = client.get(status_url)
            if status_resp.status_code != 200:
                fail(f'Processing status returned {status_resp.status_code}')
            status_data = status_resp.json()
            if status_data.get('processing_complete'):
                processing_done = True
                ok(f'Processing complete (pending={status_data.get("pending_count")})')
                break
            pending = status_data.get('pending_count', '?')
            print(f'  ... waiting, {pending} pending')
            time.sleep(3)

        if not processing_done:
            fail('Processing did not complete within 300s (infinite loading risk)')

        results = client.get(complete_url)
        if results.status_code != 200:
            fail(f'Results page returned {results.status_code}')
        html = results.content.decode('utf-8', errors='replace')

        if 'Processing Your Results' in html:
            fail('Still on processing page after processing_complete')

        assessment = IndividualAssessment.objects.get(session_id=session_id)
        assessment.refresh_from_db()

        ok(f'Assessment status={assessment.status}, overall={assessment.overall_score}')
        ok(f'  speaking={assessment.speaking_score}, body={assessment.body_language_score}, attire={assessment.attire_score}')

        if assessment.overall_score is None:
            fail('overall_score is None on results page')

        fake_pairs = {(6.0, 8.0), (8.0, 6.0)}
        bl, at = assessment.body_language_score, assessment.attire_score
        if bl is not None and at is not None and (round(bl, 1), round(at, 1)) in fake_pairs:
            fail(f'Suspicious fallback scores detected: body={bl}, attire={at}')

        if 'AI Feedback Summary' not in html:
            fail('Results page missing AI Feedback Summary section')

        if GEMINI_FALLBACK_SNIPPET in html:
            print('WARN: Gemini fallback feedback text detected (API may have failed)')

        if 'csrf' in html.lower() and '403' in html:
            fail('CSRF error visible in results HTML')

        # Per-response checks
        for resp in assessment.responses.order_by('question_order'):
            ad = resp.analysis_data or {}
            est = ad.get('audio_est_bytes', 0)
            sp = ad.get('speech_analysis', {})
            transcript = (sp.get('transcription') or '').strip()
            status = ad.get('speech_analysis_status')
            if est < 10000:
                fail(f'Response Q{resp.question_order}: audio_est_bytes={est} (<10000)')
            if status != 'completed':
                fail(f'Response Q{resp.question_order}: speech status={status}')
            if sp.get('error'):
                fail(f'Response Q{resp.question_order}: speech error={sp.get("error")}')
            ok(f'Q{resp.question_order}: {est} bytes, transcript={transcript[:60]!r}...')

        print(f'\n=== E2E PASSED session_id={session_id} assessment_id={assessment.id} ===')
        print('Run: python investigate_db.py')


if __name__ == '__main__':
    main()
