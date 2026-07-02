"""
End-to-end CSRF test for combined assessment snapshot + audio submission.
Uses Django test client with enforce_csrf_checks=True (same as production).
"""
import base64
import json
import os
import sys
import uuid

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')

import django
django.setup()

from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.utils import timezone

from AnalysisAPI.models import (
    IndividualAssessment,
    IndividualAssessmentResponse,
    AssessmentSnapshot,
    PlatformJobTitle,
    PlatformQuestion,
)

User = get_user_model()

# Minimal 1x1 JPEG as base64 (valid image for snapshot endpoint)
TINY_JPEG_B64 = (
    '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof'
    'Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwh'
    'MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAAR'
    'CAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAA'
    'AAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMB'
    'AAIRAxEAPwCwAA8A/9k='
)

# Simulated WebM-ish payload (>1KB decoded) — not real audio, but tests storage path
FAKE_AUDIO_B64 = base64.b64encode(b'\x00' * 4096).decode('ascii')


def fail(msg):
    print(f'FAIL: {msg}')
    sys.exit(1)


def ok(msg):
    print(f'OK: {msg}')


def get_or_create_fixture():
    user = User.objects.filter(is_active=True).first()
    if not user:
        fail('No active user in database — log in once via the app first')

    job_title = PlatformJobTitle.objects.filter(is_active=True).first()
    if not job_title:
        fail('No active PlatformJobTitle in database')

    if not PlatformQuestion.objects.filter(job_title=job_title).exists():
        PlatformQuestion.objects.create(
            job_title=job_title,
            question_text='Describe a challenging project you completed.',
            question_type='behavioral',
            is_mandatory=True,
            order=1,
        )

    assessment = IndividualAssessment.objects.create(
        user=user,
        platform_job_title=job_title,
        status='in_progress',
        started_at=timezone.now(),
    )
    assessment.select_questions()
    question = PlatformQuestion.objects.filter(job_title=job_title).first()
    return user, assessment, question


def main():
    user, assessment, question = get_or_create_fixture()
    session_id = assessment.session_id

    with override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1']):
        client = Client(enforce_csrf_checks=True)

        logged_in = client.login(username=user.username, password='testpass123')
        if not logged_in:
            logged_in = client.login(username=user.email, password='testpass123')
        if not logged_in:
            print(f'Note: could not login as {user.username!r} with testpass123 — using force_login')
            client.force_login(user)

        # Load combined assessment page — sets csrftoken cookie + hidden form token
        page_url = f'/analysis/assessment/{session_id}/combined/'
        page = client.get(page_url)
        if page.status_code != 200:
            fail(f'GET {page_url} returned {page.status_code}')

        if 'csrfmiddlewaretoken' not in page.content.decode('utf-8', errors='replace'):
            fail('combined_assessment.html missing csrfmiddlewaretoken in rendered page')

        csrf_cookie = client.cookies.get('csrftoken')
        if not csrf_cookie:
            fail('csrftoken cookie not set after loading combined assessment page')
        csrf_token = csrf_cookie.value
        ok(f'csrftoken cookie present ({len(csrf_token)} chars)')

        snapshot_url = f'/analysis/combined-snapshot/{session_id}/'
        snapshot_body = json.dumps({
            'image_data': f'data:image/jpeg;base64,{TINY_JPEG_B64}',
            'analysis_type': 'body_language',
            'question_id': question.id,
        })

        blocked = client.post(
            snapshot_url,
            data=snapshot_body,
            content_type='application/json',
        )
        if blocked.status_code != 403:
            fail(f'POST snapshot without CSRF should be 403, got {blocked.status_code}: {blocked.content[:200]}')
        ok('snapshot blocked without CSRF token (403)')

        snap_resp = client.post(
            snapshot_url,
            data=snapshot_body,
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        if snap_resp.status_code != 200:
            fail(f'POST snapshot with CSRF failed: {snap_resp.status_code} {snap_resp.content[:300]}')
        snap_data = snap_resp.json()
        if not snap_data.get('success'):
            fail(f'Snapshot endpoint error: {snap_data}')
        ok(f'snapshot saved (id={snap_data.get("snapshot_id")})')

        response_url = f'/analysis/combined-response/{session_id}/'
        audio_body = json.dumps({
            'question_id': question.id,
            'audio_data': FAKE_AUDIO_B64,
            'response_time': 5,
            'fullscreen_violations': 0,
        })

        audio_blocked = client.post(
            response_url,
            data=audio_body,
            content_type='application/json',
        )
        if audio_blocked.status_code != 403:
            fail(f'POST audio without CSRF should be 403, got {audio_blocked.status_code}')
        ok('audio submission blocked without CSRF token (403)')

        audio_resp = client.post(
            response_url,
            data=audio_body,
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        if audio_resp.status_code != 200:
            fail(f'POST audio with CSRF failed: {audio_resp.status_code} {audio_resp.content[:300]}')
        audio_data = audio_resp.json()
        if not audio_data.get('success'):
            fail(f'Audio endpoint error: {audio_data}')
        ok(f'audio response saved (response_id={audio_data.get("response_id")})')

        resp_obj = IndividualAssessmentResponse.objects.get(id=audio_data['response_id'])
        ad = resp_obj.analysis_data or {}
        est_bytes = ad.get('audio_est_bytes')
        b64_len = ad.get('audio_b64_length')
        if not est_bytes or est_bytes < 1024:
            fail(f'audio_est_bytes too small or missing: {est_bytes!r} (analysis_data={ad})')
        if b64_len != len(FAKE_AUDIO_B64):
            fail(f'audio_b64_length mismatch: stored {b64_len}, sent {len(FAKE_AUDIO_B64)}')
        ok(f'audio metadata stored: b64_len={b64_len}, est_bytes={est_bytes}')

        snap_count = AssessmentSnapshot.objects.filter(assessment=assessment).count()
        if snap_count < 1:
            fail('No snapshots in DB for test assessment')
        ok(f'{snap_count} snapshot(s) in DB for test assessment')

        print(f'\nTest assessment session_id={session_id} (id={assessment.id})')
        print('Run: python investigate_db.py')
        print('All CSRF + snapshot + audio checks passed.')


if __name__ == '__main__':
    main()
