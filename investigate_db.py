"""
investigate_db.py — Always queries the most recent assessment.
Shows audio size, uniqueness, speech results, duration, and snapshot scores.
"""
import sys
import json
import base64
import hashlib
import sqlite3
import datetime
import traceback
import os

# Write to both terminal and file so output is captured regardless of shell issues
_outfile = open('investigate_output.txt', 'w', encoding='utf-8')

def tprint(*args, **kwargs):
    """Print to both stdout and the output file."""
    print(*args, **kwargs)
    print(*args, **kwargs, file=_outfile)
    _outfile.flush()

tprint("Script started")

try:
    db_path = os.path.join(os.path.dirname(__file__), 'db.sqlite3')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM AnalysisAPI_individualassessment ORDER BY started_at DESC LIMIT 1")
    assessment = cursor.fetchone()

    if not assessment:
        tprint("No assessments found.")
        sys.exit(0)

    tprint(f"=== Assessment: {assessment['id']} ===")
    tprint(f"  status    : {assessment['status']}")
    tprint(f"  overall   : {assessment['overall_score']}")
    tprint(f"  speaking  : {assessment['speaking_score']}")
    tprint(f"  body lang : {assessment['body_language_score']}")
    tprint(f"  attire    : {assessment['attire_score']}")
    tprint(f"  started   : {assessment['started_at']}")
    tprint(f"  completed : {assessment['completed_at']}")

    if assessment['started_at'] and assessment['completed_at']:
        try:
            start = datetime.datetime.fromisoformat(assessment['started_at'].replace('+00:00', ''))
            end = datetime.datetime.fromisoformat(assessment['completed_at'].replace('+00:00', ''))
            secs = (end - start).total_seconds()
            tprint(f"  duration  : {secs:.1f}s  ({secs/60:.2f} min)")
            if secs < 60:
                tprint(f"  display would show: {int(secs)} seconds")
            else:
                tprint(f"  display would show: {int(secs // 60)} minutes")
        except Exception as e:
            tprint("Could not parse dates", e)

    tprint("\n--- Responses ---")
    cursor.execute(
        "SELECT * FROM AnalysisAPI_individualassessmentresponse WHERE assessment_id = ? ORDER BY question_order",
        (assessment['id'],),
    )
    responses = cursor.fetchall()
    hashes = {}
    full_b64_strings = {}

    for r in responses:
        ad = json.loads(r['analysis_data']) if r['analysis_data'] else {}
        sp = ad.get('speech_analysis', {})

        # Prefer metadata fields; fall back to stored base64 string
        b64_len = ad.get('audio_b64_length')
        est_bytes = ad.get('audio_est_bytes')
        full_audio = ad.get('audio_base64', '')
        preview = ad.get('audio_base64_preview', '')

        if b64_len is None and full_audio:
            b64_len = len(full_audio)
        if est_bytes is None and b64_len:
            est_bytes = (b64_len * 3) // 4

        dbg = ad.get('debug_audio', {})
        if dbg.get('base64_len'):
            b64_len = dbg['base64_len']
            est_bytes = dbg.get('bytes_len', est_bytes)

        truncated = bool(full_audio.endswith('...') or preview.endswith('...'))
        if dbg.get('hash'):
            full_hash = dbg['hash'][:12]
        else:
            hash_source = full_audio if full_audio and not truncated else preview.replace('...', '')
            full_hash = hashlib.md5(hash_source.encode()).hexdigest()[:12] if hash_source else 'N/A'
        hashes[r['question_order']] = full_hash
        full_b64_strings[r['question_order']] = full_audio

        tprint(f"\n  Q{r['question_order']} (response id={r['id']}):")
        tprint(f"    audio_b64_length  : {b64_len if b64_len is not None else 'NOT STORED'}")
        tprint(f"    audio_est_bytes   : {est_bytes if est_bytes is not None else 'NOT STORED'}")
        tprint(f"    stored truncated  : {truncated}")
        tprint(f"    content hash      : {full_hash}")
        tprint(f"    debug_audio       : {dbg if dbg else 'none'}")
        tprint(f"    speech_status     : {ad.get('speech_analysis_status', 'missing')}")
        tprint(f"    speech error      : {sp.get('error', 'none')}")
        tprint(f"    transcription     : '{sp.get('transcription', '')}'")

    tprint("\n--- Audio Uniqueness Check ---")
    unique_hashes = set(hashes.values())
    tprint(f"  Unique content hashes: {len(unique_hashes)} out of {len(hashes)} responses")
    for q, h in hashes.items():
        tprint(f"    Q{q}: {h}")

    lengths = set()
    for r in responses:
        ad = json.loads(r['analysis_data']) if r['analysis_data'] else {}
        dbg = ad.get('debug_audio', {})
        ln = dbg.get('bytes_len') or ad.get('audio_est_bytes') or ad.get('audio_b64_length')
        if ln is not None:
            lengths.add(ln)
    if len(lengths) > 1:
        tprint(f"  Distinct audio sizes (bytes/b64_len): {sorted(lengths)}")
        tprint("  OK: Responses have different audio payload sizes")
    elif len(unique_hashes) == 1 and len(hashes) > 1 and 'N/A' not in unique_hashes:
        max_bytes = 0
        for r in responses:
            ad = json.loads(r['analysis_data']) if r['analysis_data'] else {}
            dbg = ad.get('debug_audio', {})
            ln = dbg.get('bytes_len') or ad.get('audio_est_bytes') or 0
            max_bytes = max(max_bytes, ln)
        if max_bytes < 1024:
            tprint("  *** All responses share identical tiny/truncated audio — likely empty WebM header only ***")
        elif max_bytes >= 10000:
            tprint("  NOTE: Identical audio hash across questions (same clip reused per question — OK for automated tests)")
        else:
            tprint("  *** WARNING: All responses share identical full audio — duplicate audio bug ***")
    elif len(unique_hashes) == len(hashes):
        tprint("  OK: Each response has distinct audio content")

    # Compare full base64 strings when not truncated
    stored_full = [v for v in full_b64_strings.values() if v and not v.endswith('...')]
    if len(stored_full) >= 2:
        all_same = all(s == stored_full[0] for s in stored_full)
        tprint(f"  Full base64 strings identical: {all_same}")

    tprint("\n--- Snapshots ---")
    cursor.execute("SELECT * FROM AnalysisAPI_assessmentsnapshot WHERE assessment_id = ?", (assessment['id'],))
    snaps = cursor.fetchall()
    tprint(f"  Total: {len(snaps)}")
    body_scores = []
    attire_scores = []
    for s in snaps:
        ad = json.loads(s['analysis_data']) if s['analysis_data'] else {}
        result = ad.get('analysis_result', ad if isinstance(ad, dict) else {})
        if not isinstance(result, dict):
            result = {}
        col_score = s['score']
        result_score = result.get('overall_score')
        if s['analysis_type'] == 'body_language' and result_score is not None:
            body_scores.append(result_score)
        if s['analysis_type'] == 'attire' and result_score is not None:
            attire_scores.append(result_score)
        if len(snaps) <= 10 or s['id'] == snaps[0]['id']:
            tprint(f"  id={s['id']} type={s['analysis_type']} col_score={col_score} result_overall={result_score}")

    if body_scores:
        avg = sum(body_scores) / len(body_scores)
        tprint(f"  body_language result_overall avg: {avg:.3f} (n={len(body_scores)})")
    if attire_scores:
        avg = sum(attire_scores) / len(attire_scores)
        tprint(f"  attire result_overall avg: {avg:.3f} (n={len(attire_scores)})")

    conn.close()
    tprint("\nDone.")

except Exception:
    tprint("\n=== EXCEPTION OCCURRED ===")
    traceback.print_exc()
    traceback.print_exc(file=_outfile)
    _outfile.flush()
    sys.exit(1)
finally:
    _outfile.close()

