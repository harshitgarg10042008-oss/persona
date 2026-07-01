"""Verify speech pipeline with a real audio sample generated via ffmpeg."""
import os
import subprocess
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisModules.speech_analyzer import WebSpeechAnalyzer

SAMPLE_PATH = os.path.join(os.path.dirname(__file__), 'verify_sample.webm')

# Generate 3 seconds of speech-like tone (ffmpeg lavfi annullsrc won't have speech;
# use sine + volume as minimal valid webm for pipeline test, then note whisper needs real speech)
if not os.path.exists(SAMPLE_PATH) or os.path.getsize(SAMPLE_PATH) < 1024:
    cmd = [
        'ffmpeg', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3',
        '-c:a', 'libopus', '-b:a', '64k', SAMPLE_PATH,
    ]
    print('Generating sample:', ' '.join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print('ffmpeg failed:', r.stderr)
        sys.exit(1)

size = os.path.getsize(SAMPLE_PATH)
print(f'Sample file: {SAMPLE_PATH} ({size} bytes)')

r = subprocess.run(
    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', SAMPLE_PATH],
    capture_output=True, text=True,
)
print(f'ffprobe duration: {r.stdout.strip()}s')

with open(SAMPLE_PATH, 'rb') as f:
    audio_bytes = f.read()

analyzer = WebSpeechAnalyzer()
analyzer.initialize_models()
result = analyzer.analyze_audio(audio_bytes, 'Tell me about yourself', 3)
print('analyze_audio result:')
print(f"  error: {result.get('error')}")
print(f"  transcription: {result.get('transcription')!r}")
print(f"  word_count: {result.get('word_count')}")
print(f"  overall_score: {result.get('overall_score')}")

# Task decode path
from AnalysisModules.AnalysisAPI.tasks import _decode_audio_base64, run_speech_analysis_task
import base64
b64 = base64.b64encode(audio_bytes).decode()
decoded = _decode_audio_base64(b64)
print(f'task decode: {len(decoded)} bytes (match={len(decoded)==len(audio_bytes)})')

print('\nMediaPipe check:')
from AnalysisModules.body_language_analyzer import body_language_analyzer
print(f'  mediapipe_available: {body_language_analyzer.mediapipe_available}')
body_language_analyzer.initialize_detectors()
print(f'  detectors initialized: {body_language_analyzer.is_initialized}')
