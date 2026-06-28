"""
investigate_db.py — Always queries the most recent assessment.
Shows audio size, uniqueness, speech results, duration, and snapshot scores.
"""
import os
import sys
import json
import base64
import hashlib

import sys
# Redirect all output to a file to bypass shell redirection issues
sys.stdout = open('C:/Users/vishe/OneDrive/Desktop/Samyak/persona/db_output.txt', 'w', encoding='utf-8')

sys.path.insert(0, r"c:\Users\vishe\OneDrive\Desktop\Samyak\persona")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
import django
django.setup()

from AnalysisModules.AnalysisAPI.models import IndividualAssessment, AssessmentSnapshot

assessment = IndividualAssessment.objects.order_by('-started_at').first()
if not assessment:
    print("No assessments found.")
    sys.exit(0)

print(f"=== Assessment: {assessment} ===")
print(f"  status    : {assessment.status}")
print(f"  overall   : {assessment.overall_score}")
print(f"  speaking  : {assessment.speaking_score}")
print(f"  body lang : {assessment.body_language_score}")
print(f"  attire    : {assessment.attire_score}")
print(f"  started   : {assessment.started_at}")
print(f"  completed : {assessment.completed_at}")

if assessment.started_at and assessment.completed_at:
    secs = (assessment.completed_at - assessment.started_at).total_seconds()
    print(f"  duration  : {secs:.1f}s  ({secs/60:.2f} min)")
    print(f"  display would show: {'%d seconds' % secs if secs < 60 else '%d minutes' % (secs//60)}")

print("\n--- Responses ---")
responses = assessment.responses.all().order_by('question_order')
hashes = {}
for r in responses:
    ad = r.analysis_data or {}
    sp = ad.get('speech_analysis', {})
    
    # Try to get the full audio_base64 if it's there
    full_audio = ad.get('audio_base64', '')
    if full_audio:
        b64_len = len(full_audio)
        est_bytes = (b64_len * 3) // 4
        # We also want the hash of the FULL string
        full_hash = hashlib.md5(full_audio.encode()).hexdigest()[:8]
    else:
        # Fallback to the saved length if full base64 was cleared
        b64_len = ad.get('audio_b64_length', 0)
        est_bytes = ad.get('audio_est_bytes', 0)
        full_hash = "N/A (base64 cleared)"
        
    preview = ad.get('audio_base64_preview', ad.get('audio_base64', 'NONE'))[:60]
    preview_hash = hashlib.md5(preview.encode()).hexdigest()[:8] if preview else 'N/A'
    hashes[r.question_order] = full_hash
    
    print(f"\n  Q{r.question_order}:")
    print(f"    audio_b64_length  : {b64_len}")
    print(f"    audio_est_bytes   : {est_bytes}")
    print(f"    full string hash  : {full_hash}")
    print(f"    preview hash      : {preview_hash}")
    print(f"    speech_status     : {ad.get('speech_analysis_status', 'missing')}")
    print(f"    speech error      : {sp.get('error', 'none')}")
    print(f"    transcription     : '{sp.get('transcription', '')}'")
    print(f"    overall_score     : {sp.get('overall_score', 'N/A')}")

print("\n--- Audio Uniqueness Check ---")
unique = set(hashes.values())
print(f"  Unique preview hashes: {len(unique)} out of {len(hashes)} responses")
for q, h in hashes.items():
    print(f"    Q{q}: {h}")
if len(unique) == 1 and len(hashes) > 1:
    print("  *** WARNING: All responses share same audio prefix — duplicate audio bug ***")

print("\n--- Snapshots ---")
snaps = AssessmentSnapshot.objects.filter(assessment=assessment)
print(f"  Total: {snaps.count()}")
for s in snaps:
    ad = s.analysis_data or {}
    result = ad.get('analysis_result', {})
    print(f"  id={s.id} type={s.analysis_type} score={s.score} | result_keys={list(result.keys()) if isinstance(result, dict) else result}")
