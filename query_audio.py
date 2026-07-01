import sqlite3, json, hashlib, base64

conn = sqlite3.connect('db.sqlite3')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute('SELECT * FROM AnalysisAPI_individualassessment ORDER BY started_at DESC LIMIT 1')
a = c.fetchone()
print('Assessment', a['id'])
c.execute('SELECT id, question_order, analysis_data FROM AnalysisAPI_individualassessmentresponse WHERE assessment_id=? ORDER BY question_order', (a['id'],))
hashes = {}
for r in c.fetchall():
    ad = json.loads(r['analysis_data']) if r['analysis_data'] else {}
    q = r['question_order']
    b64_len = ad.get('audio_b64_length', len(ad.get('audio_base64', '')))
    est = ad.get('audio_est_bytes', (b64_len * 3) // 4)
    dbg = ad.get('debug_audio', {})
    prev = ad.get('audio_base64_preview', ad.get('audio_base64', ''))
    h = dbg.get('hash') or (hashlib.md5(prev.encode()).hexdigest() if prev else 'N/A')
    hashes[q] = h
    print(f"Q{q} id={r['id']} b64_len={b64_len} est_bytes={est} hash={h[:16]}")
    print(f"  debug_audio={dbg}")
    print(f"  preview={repr(prev[:80])}")
    sp = ad.get('speech_analysis', ad)
    print(f"  speech_error={sp.get('error', 'none')}")

print("\nUnique hashes:", len(set(hashes.values())), "of", len(hashes))
print("All identical:", len(set(hashes.values())) == 1)

# Try decode preview as webm
prev = json.loads(c.execute('SELECT analysis_data FROM AnalysisAPI_individualassessmentresponse WHERE assessment_id=? ORDER BY question_order LIMIT 1', (a['id'],)).fetchone()[0])
preview = prev.get('audio_base64_preview', '')
if preview.endswith('...'):
    print("\nCannot decode truncated preview")
else:
    try:
        raw = preview
        if 'base64,' in raw:
            raw = raw.split('base64,')[1]
        data = base64.b64decode(raw)
        with open('test_from_preview.webm', 'wb') as f:
            f.write(data)
        print(f"\nDecoded preview: {len(data)} bytes")
    except Exception as e:
        print(f"Decode error: {e}")

conn.close()
