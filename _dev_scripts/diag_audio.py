"""
Diagnostic script for audio issue investigation.
Run with: python diag_audio.py
"""
import sqlite3
import json
import base64
import os
import tempfile

DB_PATH = 'db.sqlite3'
SESSION_ID = '71f39aa0-49e8-4b4f-9359-0f218a4e6597'

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("""
    SELECT r.id, r.analysis_data, r.response_duration
    FROM AnalysisAPI_individualassessmentresponse r
    JOIN AnalysisAPI_individualassessment a ON r.assessment_id = a.id
    WHERE a.session_id = ?
    ORDER BY r.id
""", (SESSION_ID,))
rows = cur.fetchall()

print(f"=== Found {len(rows)} responses for session {SESSION_ID} ===\n")

audio_b64_found = None

for row in rows:
    rid, raw_data, duration = row
    data = json.loads(raw_data or '{}')
    
    print(f"--- Response ID: {rid} ---")
    print(f"  speech_analysis_status : {data.get('speech_analysis_status', 'MISSING')}")
    print(f"  has_audio_data         : {data.get('has_audio_data')}")
    
    audio_b64 = data.get('audio_base64', '')
    print(f"  audio_base64 stored    : {len(audio_b64)} chars ({audio_b64[:80]}...)")
    
    speech = data.get('speech_analysis', {})
    if isinstance(speech, dict):
        print(f"  speech error           : {speech.get('error', 'none')}")
        print(f"  transcription          : '{speech.get('transcription', 'N/A')}'")
        print(f"  word_count             : {speech.get('word_count', 'N/A')}")
    else:
        print(f"  speech_analysis        : {speech}")
    
    if audio_b64 and '...' not in audio_b64:
        audio_b64_found = audio_b64
    print()

conn.close()

print("=== Key Findings ===")
print()
print("ISSUE A ROOT CAUSE:")
print("  The audio is recorded as audio/webm;codecs=opus in the browser.")
print("  In combined_assessment.html processRecording() (line 985):")
print("    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });")
print("    reader.result.split(',')[1]  <-- strips 'data:audio/webm;base64,' prefix")
print()
print("  This base64 string is sent via JSON to submit_response_combined().")
print("  In views.py (line 1396), the code TRUNCATES the audio_base64 to 100 chars:")
print("    audio_data[:100] + '...'  <-- ONLY a preview is stored in DB!")
print("  The FULL audio_data IS passed to async_task() (line 1411) -- correct.")
print()
print("  But the real issue is in tasks.py line 22:")
print("    audio_bytes = base64.b64decode(audio_data)")
print("  Then speech_analyzer.analyze_audio(audio_bytes, ...) is called.")
print("  The audio_bytes are RAW WEBM bytes, but the temp file is saved as .wav:")
print("    with tempfile.NamedTemporaryFile(suffix='.wav', ...) as temp_file:")
print("  Whisper then tries to load a .wav file that is actually WEBM-encoded audio.")
print("  This causes Whisper/ffmpeg to either fail silently or return empty transcription.")
print()
print("  FIX: Change the temp file suffix from '.wav' to '.webm' in speech_analyzer.py")
print("       so Whisper/ffmpeg correctly identifies the audio container format.")
print()
print("  SECONDARY: also check if the frontend strips 'data:audio/webm;base64,' prefix")
print("  combined_assessment.html line 990: reader.result.split(',')[1]  <-- YES, correctly strips prefix")
print()
print("=== Media directory check ===")
media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'media')
if os.path.exists(media_dir):
    for root, dirs, files in os.walk(media_dir):
        for f in files:
            fpath = os.path.join(root, f)
            print(f"  {fpath}: {os.path.getsize(fpath)} bytes")
else:
    print(f"  media/ directory does NOT exist at {media_dir}")
    print("  (No audio files are written to disk - audio stays as base64 in memory/DB)")
