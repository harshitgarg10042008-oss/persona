import sqlite3, json, hashlib, datetime, sys

OUTPUT_FILE = "diag_run_output.txt"

lines = []

db_path = 'db.sqlite3'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get latest assessment
cursor.execute("SELECT * FROM AnalysisAPI_individualassessment ORDER BY started_at DESC LIMIT 1")
assessment = cursor.fetchone()

if not assessment:
    lines.append("No assessments found.")
else:
    lines.append(f"=== Assessment: {assessment['id']} ===")
    lines.append(f"  status    : {assessment['status']}")
    lines.append(f"  overall   : {assessment['overall_score']}")
    lines.append(f"  speaking  : {assessment['speaking_score']}")
    lines.append(f"  body lang : {assessment['body_language_score']}")
    lines.append(f"  attire    : {assessment['attire_score']}")
    lines.append(f"  started   : {assessment['started_at']}")
    lines.append(f"  completed : {assessment['completed_at']}")
    
    if assessment['started_at'] and assessment['completed_at']:
        try:
            start = datetime.datetime.fromisoformat(assessment['started_at'].replace('+00:00',''))
            end = datetime.datetime.fromisoformat(assessment['completed_at'].replace('+00:00',''))
            secs = (end - start).total_seconds()
            lines.append(f"  duration  : {secs:.1f}s  ({secs/60:.2f} min)")
            if secs < 60:
                lines.append(f"  display would show: {int(secs)} seconds  [WOULD SHOW 0 MINUTES - BUG NEEDS FIX]")
            else:
                lines.append(f"  display would show: {int(secs//60)} minutes")
        except Exception as e:
            lines.append(f"  Could not parse dates: {e}")

    lines.append("\n--- Responses ---")
    cursor.execute("SELECT * FROM AnalysisAPI_individualassessmentresponse WHERE assessment_id = ? ORDER BY question_order", (assessment['id'],))
    responses = cursor.fetchall()
    
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
            full_hash = "N/A (base64 cleared - stored as length only)"
            
        preview = ad.get('audio_base64_preview', ad.get('audio_base64', 'NONE'))
        if preview:
            preview_60 = preview[:60]
            preview_hash = hashlib.md5(preview.encode()).hexdigest()[:8]
        else:
            preview_60 = 'NONE'
            preview_hash = 'N/A'
        
        hashes[r['question_order']] = full_hash
        
        lines.append(f"\n  Q{r['question_order']}:")
        lines.append(f"    audio_b64_length  : {b64_len}")
        lines.append(f"    audio_est_bytes   : {est_bytes}  ({est_bytes/1024:.1f} KB)")
        lines.append(f"    full string hash  : {full_hash}")
        lines.append(f"    preview_60chars   : {preview_60}")
        lines.append(f"    preview hash (60c): {preview_hash}")
        lines.append(f"    speech_status     : {ad.get('speech_analysis_status', 'MISSING')}")
        lines.append(f"    speech error      : {sp.get('error', 'none')}")
        lines.append(f"    transcription     : '{sp.get('transcription', '')}'")
        lines.append(f"    overall_score     : {sp.get('overall_score', 'N/A')}")
        lines.append(f"    all keys in ad    : {list(ad.keys())}")

    lines.append("\n--- Audio Uniqueness Check ---")
    unique_hashes = set(hashes.values())
    lines.append(f"  Unique hashes: {len(unique_hashes)} out of {len(hashes)} responses")
    for q, h in hashes.items():
        lines.append(f"    Q{q}: {h}")
    if len(unique_hashes) == 1 and len(hashes) > 1:
        lines.append("  *** WARNING: All responses share same audio hash — duplicate audio bug ***")
    elif len(unique_hashes) == len(hashes):
        lines.append("  *** OK: Each response has unique audio ***")
    
    lines.append("\n--- Snapshots ---")
    cursor.execute("SELECT * FROM AnalysisAPI_assessmentsnapshot WHERE assessment_id = ?", (assessment['id'],))
    snaps = cursor.fetchall()
    lines.append(f"  Total snapshots: {len(snaps)}")
    for s in snaps:
        ad = json.loads(s['analysis_data']) if s['analysis_data'] else {}
        result = ad.get('analysis_result', {})
        keys = list(result.keys()) if isinstance(result, dict) else result
        lines.append(f"  id={s['id']} type={s['analysis_type']} score={s['score']} | result_keys={keys}")
    
    # Also check the total snapshot count for all types
    cursor.execute("SELECT analysis_type, COUNT(*), AVG(score) FROM AnalysisAPI_assessmentsnapshot WHERE assessment_id = ? GROUP BY analysis_type", (assessment['id'],))
    snap_agg = cursor.fetchall()
    lines.append("\n--- Snapshot Aggregation ---")
    for row in snap_agg:
        lines.append(f"  type={row[0]} count={row[1]} avg_score={row[2]}")

conn.close()

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"Output written to {OUTPUT_FILE}")
