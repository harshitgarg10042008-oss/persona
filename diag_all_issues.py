"""
Comprehensive diagnostic script for all 3 issues.
Run with: venv\Scripts\python.exe diag_all_issues.py
"""
import os
import sys
import json
import base64
import hashlib
import subprocess
import tempfile

import sys
sys.path.insert(0, r"c:\Users\vishe\OneDrive\Desktop\Samyak\persona")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')

import django
django.setup()

from django.db import connection
from AnalysisModules.AnalysisAPI.models import IndividualAssessment, IndividualAssessmentResponse

# =========================================================
# ISSUE 1 — Audio analysis evidence
# =========================================================
print("=" * 60)
print("ISSUE 1: AUDIO INVESTIGATION")
print("=" * 60)

assessment = IndividualAssessment.objects.order_by('-started_at').first()
if not assessment:
    print("No assessments found.")
    sys.exit(1)

print(f"Assessment: {assessment} | status={assessment.status}")
print(f"Started:    {assessment.started_at}")
print(f"Completed:  {assessment.completed_at}")

if assessment.started_at and assessment.completed_at:
    secs = (assessment.completed_at - assessment.started_at).total_seconds()
    print(f"Duration:   {secs:.2f}s  ({secs/60:.3f} min)")

responses = list(assessment.responses.all().order_by('question_order'))
print(f"\nTotal responses: {len(responses)}")

audio_hashes = {}
first_audio_bytes = None
first_audio_qn = None

for r in responses:
    ad = r.analysis_data or {}
    sp = ad.get('speech_analysis', {})
    
    # The stored audio_base64 in analysis_data is TRUNCATED (first 100 chars + "...")
    # so we check analysis_data['audio_base64'] just for the prefix.
    stored_b64_preview = ad.get('audio_base64', 'NOT STORED')
    
    print(f"\n  Q{r.question_order}:")
    print(f"    stored audio_base64 preview : {stored_b64_preview[:80]}")
    print(f"    speech_analysis_status      : {ad.get('speech_analysis_status', 'missing')}")
    print(f"    speech error                : {sp.get('error', 'none')}")
    print(f"    transcription               : '{sp.get('transcription', '')}'")
    print(f"    word_count                  : {sp.get('word_count', 'N/A')}")
    print(f"    overall_score               : {sp.get('overall_score', 'N/A')}")

# =========================================================
# Re-decode from the DB to get ACTUAL audio size.
# Since analysis_data only stores 100-char preview, we need
# to check if the full audio_data was passed to the task.
# We'll re-run analyze_speech on the latest task's stored data
# by checking django_q ORM tables.
# =========================================================
print("\n--- Checking django_q task queue for speech analysis tasks ---")
try:
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, name, func, args, result, started, stopped, success, attempt_count
            FROM django_q_task
            ORDER BY stopped DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                tid, name, func, args_raw, result, started, stopped, success, attempts = row
                print(f"  task={func} | success={success} | started={started} | stopped={stopped}")
                if args_raw and 'run_speech_analysis' in (func or ''):
                    try:
                        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                        print(f"    args[0] (response_id): {args[0] if args else 'N/A'}")
                        if args and len(args) > 1:
                            audio_arg = args[1]
                            print(f"    args[1] (audio_data) length: {len(audio_arg)} chars | est bytes: {int(len(audio_arg)*3/4)}")
                            if first_audio_bytes is None:
                                try:
                                    first_audio_bytes = base64.b64decode(audio_arg)
                                    first_audio_qn = "from_task_queue"
                                    print(f"    -> DECODED: {len(first_audio_bytes)} bytes ({len(first_audio_bytes)/1024:.2f} KB)")
                                except Exception as e:
                                    print(f"    -> Decode failed: {e}")
                    except Exception as e:
                        print(f"    Could not parse args: {e}")
        else:
            print("  No tasks in django_q_task table.")
except Exception as e:
    print(f"  django_q query failed: {e}")

# Also check the ORM model
print("\n--- Checking django_q Success table ---")
try:
    from django_q.models import Success, Failure
    tasks = Success.objects.filter(func__icontains='speech').order_by('-stopped')[:5]
    print(f"  Successful speech tasks: {tasks.count()}")
    for t in tasks:
        print(f"    id={t.id} | stopped={t.stopped} | result={str(t.result)[:100]}")
    
    failures = Failure.objects.filter(func__icontains='speech').order_by('-stopped')[:5]
    print(f"  Failed speech tasks: {failures.count()}")
    for t in failures:
        print(f"    id={t.id} | stopped={t.stopped} | attempt={t.attempt_count}")
        print(f"    error: {str(t.result)[:200] if t.result else 'no result'}")
except Exception as e:
    print(f"  django_q model query failed: {e}")

# =========================================================
# Direct Whisper test with synthetic audio
# =========================================================
print("\n--- Direct Whisper test (synthetic short .webm) ---")
# Use the existing test_audio.webm (75 bytes, known bad) for comparison,
# then try running whisper directly on it to confirm what error comes out.
test_path = r"C:\Users\vishe\OneDrive\Desktop\Samyak\persona\test_audio.webm"
if os.path.exists(test_path):
    size = os.path.getsize(test_path)
    print(f"  test_audio.webm exists: {size} bytes")
    
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1',
         test_path],
        capture_output=True, text=True
    )
    print(f"  ffprobe stdout: {result.stdout.strip()}")
    print(f"  ffprobe stderr: {result.stderr.strip()[:200]}")

# =========================================================
# ISSUE 2 — Duration display
# =========================================================
print("\n" + "=" * 60)
print("ISSUE 2: DURATION DISPLAY INVESTIGATION")
print("=" * 60)

# Find the assessment_results.html to check how duration is rendered
import glob
results_templates = glob.glob(
    r'C:\Users\vishe\OneDrive\Desktop\Samyak\persona\PersonaFrontend\templates\**\*result*',
    recursive=True
)
print(f"Result templates found: {results_templates}")

# Check the model field for duration
print(f"\nAssessment duration_minutes field: {assessment.duration_minutes}")
if assessment.started_at and assessment.completed_at:
    real_secs = (assessment.completed_at - assessment.started_at).total_seconds()
    print(f"Real elapsed seconds: {real_secs:.2f}")
    print(f"Real elapsed minutes: {real_secs/60:.3f}")
    print(f"duration_minutes would correctly be: {int(real_secs // 60)} minutes")
    print(f"-> If assessment took {real_secs:.0f}s, '0 minutes' IS CORRECT math, but bad UX.")
    print(f"-> Fix needed: show seconds when under 60s")

# =========================================================
# ISSUE 3 — Snapshots
# =========================================================
print("\n" + "=" * 60)
print("ISSUE 3: SNAPSHOT INVESTIGATION")
print("=" * 60)

try:
    from AnalysisModules.AnalysisAPI.models import AssessmentSnapshot
    snaps = AssessmentSnapshot.objects.filter(assessment=assessment)
    print(f"Total snapshots for this assessment: {snaps.count()}")
    
    body_snaps = snaps.filter(analysis_type='body_language')
    attire_snaps = snaps.filter(analysis_type='attire')
    print(f"  body_language: {body_snaps.count()}")
    print(f"  attire:        {attire_snaps.count()}")
    
    for s in snaps[:5]:
        ad = s.analysis_data or {}
        result = ad.get('analysis_result', {})
        print(f"\n  snapshot id={s.id} | type={s.analysis_type}")
        print(f"    result keys: {list(result.keys()) if isinstance(result, dict) else result}")
        print(f"    error: {result.get('error', 'none') if isinstance(result, dict) else 'N/A'}")
        print(f"    score: {result.get('score', result.get('overall_score', 'N/A')) if isinstance(result, dict) else result}")
        
except Exception as e:
    print(f"Snapshot query failed: {e}")
    import traceback; traceback.print_exc()

# Check mediapipe availability
print("\n--- MediaPipe check ---")
try:
    import mediapipe
    print(f"  mediapipe version: {mediapipe.__version__}")
    try:
        from mediapipe.python.solutions import pose
        print("  mediapipe.solutions.pose: OK")
    except Exception as e:
        print(f"  mediapipe.solutions.pose: FAILED - {e}")
except ImportError:
    print("  mediapipe: NOT INSTALLED")

# Check body_language_analyzer
print("\n--- Body language analyzer import test ---")
try:
    from AnalysisModules.body_language_analyzer import BodyLanguageAnalyzer
    print("  BodyLanguageAnalyzer imported OK")
    bla = BodyLanguageAnalyzer()
    print(f"  is_initialized: {bla.is_initialized}")
    if not bla.is_initialized:
        bla.initialize()
        print(f"  after initialize: {bla.is_initialized}")
except Exception as e:
    print(f"  body_language_analyzer import/init FAILED: {e}")

print("\n--- Attire analyzer import test ---")
try:
    from AnalysisModules.attire_analyzer import AttireAnalyzer
    print("  AttireAnalyzer imported OK")
    aa = AttireAnalyzer()
    print(f"  is_initialized: {aa.is_initialized}")
except Exception as e:
    print(f"  attire_analyzer import/init FAILED: {e}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
