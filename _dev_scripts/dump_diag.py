import sqlite3
import json
import hashlib
import datetime

out_path = 'c:/Users/vishe/OneDrive/Desktop/Samyak/persona/dump_out.txt'
db_path = 'c:/Users/vishe/OneDrive/Desktop/Samyak/persona/db.sqlite3'

with open(out_path, 'w', encoding='utf-8') as f:
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM AnalysisAPI_individualassessment ORDER BY started_at DESC LIMIT 1")
        assessment = cursor.fetchone()

        if not assessment:
            f.write("No assessments found.\n")
        else:
            f.write(f"=== Assessment: {assessment['id']} ===\n")
            f.write(f"  status    : {assessment['status']}\n")
            f.write(f"  overall   : {assessment['overall_score']}\n")
            
            cursor.execute("SELECT * FROM AnalysisAPI_individualassessmentresponse WHERE assessment_id = ? ORDER BY question_order", (assessment['id'],))
            responses = cursor.fetchall()
            hashes = {}
            for r in responses:
                ad = json.loads(r['analysis_data']) if r['analysis_data'] else {}
                full_audio = ad.get('audio_base64', '')
                
                # IMPORTANT: issue 1a asks for length and bytes
                b64_len = len(full_audio) if full_audio else ad.get('audio_b64_length', 0)
                est_bytes = (b64_len * 3) // 4
                
                # Check actual full base64 strings if present, or preview
                full_hash = hashlib.md5(full_audio.encode()).hexdigest()[:8] if full_audio else "N/A"
                preview = ad.get('audio_base64_preview', '')
                preview_hash = hashlib.md5(preview.encode()).hexdigest()[:8] if preview else "N/A"
                
                hashes[r['question_order']] = full_hash if full_audio else preview_hash
                
                f.write(f"\n  Q{r['question_order']}:\n")
                f.write(f"    audio_b64_length  : {b64_len} chars\n")
                f.write(f"    audio_est_bytes   : {est_bytes} bytes\n")
                f.write(f"    full string hash  : {full_hash}\n")
                f.write(f"    preview hash      : {preview_hash}\n")
                f.write(f"    speech error      : {ad.get('speech_analysis', {}).get('error', 'none')}\n")

            unique = set(hashes.values())
            f.write(f"\n  Unique hashes: {len(unique)} out of {len(hashes)} responses\n")
            for q, h in hashes.items():
                f.write(f"    Q{q}: {h}\n")
            if len(unique) == 1 and len(hashes) > 1:
                f.write("  *** WARNING: All responses share same audio prefix — duplicate audio bug ***\n")

            f.write("\n--- Snapshots ---\n")
            cursor.execute("SELECT * FROM AnalysisAPI_assessmentsnapshot WHERE assessment_id = ?", (assessment['id'],))
            snaps = cursor.fetchall()
            f.write(f"  Total: {len(snaps)}\n")
            for s in snaps:
                f.write(f"  id={s['id']} type={s['analysis_type']} score={s['score']}\n")
    except Exception as e:
        f.write(f"Error: {e}\n")
