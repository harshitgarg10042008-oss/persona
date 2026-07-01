"""Simulate speech analysis with real audio bytes (post-fix verification)."""
import os
import base64
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisAPI.models import IndividualAssessment
from AnalysisAPI.tasks import run_speech_analysis_task, _decode_audio_base64
from AnalysisAPI.views import _snapshot_score_from_data

sample_path = os.path.join(os.path.dirname(__file__), 'verify_speech.webm')
with open(sample_path, 'rb') as f:
    audio_bytes = f.read()

b64 = base64.b64encode(audio_bytes).decode()
print(f'Sample: {len(audio_bytes)} bytes, b64 len={len(b64)}')
print(f'Decode roundtrip: {len(_decode_audio_base64(b64))} bytes')

assessment = IndividualAssessment.objects.order_by('-started_at').first()
response = assessment.responses.order_by('question_order').first()
print(f'Testing on response id={response.id} Q{response.question_order} (assessment {assessment.id})')

run_speech_analysis_task(response.id, b64, response.question.question_text)
response.refresh_from_db()
sp = response.analysis_data.get('speech_analysis', {})
dbg = response.analysis_data.get('debug_audio', {})
print('debug_audio:', dbg)
print('speech error:', sp.get('error'))
print('transcription:', repr(sp.get('transcription')))
print('word_count:', sp.get('word_count'))

# Read-only snapshot score projection
snap = assessment.snapshots.filter(analysis_type='body_language').first()
if snap:
    projected = _snapshot_score_from_data(snap)
    print(f'snapshot id={snap.id} col_score={snap.score} projected={projected:.2f}')
