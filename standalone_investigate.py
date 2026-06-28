import sqlite3
import json

db_path = "c:/Users/vishe/OneDrive/Desktop/Samyak/persona/db.sqlite3"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get latest assessment
cursor.execute("SELECT * FROM AnalysisAPI_individualassessment ORDER BY started_at DESC LIMIT 1")
assessment = cursor.fetchone()

if not assessment:
    print("No assessments found.")
    exit(0)

print(f"=== Assessment: {assessment['id']} ===")
print(f"  status    : {assessment['status']}")
print(f"  overall   : {assessment['overall_score']}")
print(f"  speaking  : {assessment['speaking_score']}")
print(f"  body lang : {assessment['body_language_score']}")
print(f"  attire    : {assessment['attire_score']}")
print(f"  started   : {assessment['started_at']}")
print(f"  completed : {assessment['completed_at']}")

import datetime
if assessment['started_at'] and assessment['completed_at']:
    # Format: 2024-05-18 10:20:30.123456
    try:
        start = datetime.datetime.fromisoformat(assessment['started_at'])
        end = datetime.datetime.fromisoformat(assessment['completed_at'])
        secs = (end - start).total_seconds()
        print(f"  duration  : {secs:.1f}s  ({secs/60:.2f} min)")
        print(f"  display would show: {'%d seconds' % secs if secs < 60 else '%d minutes' % (secs//60)}")
    except Exception as e:
        print("Could not parse dates", e)

print("\n--- Responses ---")
cursor.execute("SELECT * FROM AnalysisAPI_individualassessmentresponse WHERE assessment_id = ? ORDER BY question_order", (assessment['id'],))
responses = cursor.fetchall()

import hashlib
hashes = {}
for r in responses:
    ad = json.loads(r['analysis_data']) if r['analysis_data'] else {}
    sp = ad.get('speech_analysis', {})
    
    full_audio = ad.get('audio_base64', '')
    if full_audio:
        b64_len = len(full_audio)
        est_bytes = (b64_len * 3) // 4
        full_hash = hashlib.md5(full_audio.encode()).hexdigest()[:8]
    else:
        b64_len = ad.get('audio_b64_length', 0)
        est_bytes = ad.get('audio_est_bytes', 0)
        full_hash = "N/A (base64 cleared)"
        
    preview = ad.get('audio_base64_preview', ad.get('audio_base64', 'NONE'))[:60]
    preview_hash = hashlib.md5(preview.encode()).hexdigest()[:8] if preview else 'N/A'
    hashes[r['question_order']] = full_hash
    
    print(f"\n  Q{r['question_order']}:")
    print(f"    audio_b64_length  : {b64_len}")
    print(f"    audio_est_bytes   : {est_bytes}")
    print(f"    full string hash  : {full_hash}")
    print(f"    preview hash      : {preview_hash}")
    print(f"    speech_status     : {ad.get('speech_analysis_status', 'missing')}")
    print(f"    speech error      : {sp.get('error', 'none')}")
    print(f"    transcription     : '{sp.get('transcription', '')}'")

print("\n--- Audio Uniqueness Check ---")
unique = set(hashes.values())
print(f"  Unique hashes: {len(unique)} out of {len(hashes)} responses")

print("\n--- Snapshots ---")
cursor.execute("SELECT * FROM AnalysisAPI_assessmentsnapshot WHERE assessment_id = ?", (assessment['id'],))
snaps = cursor.fetchall()
print(f"  Total: {len(snaps)}")
for s in snaps:
    ad = json.loads(s['analysis_data']) if s['analysis_data'] else {}
    result = ad.get('analysis_result', {})
    keys = list(result.keys()) if isinstance(result, dict) else result
    print(f"  id={s['id']} type={s['analysis_type']} score={s['score']} | result_keys={keys}")

conn.close()
