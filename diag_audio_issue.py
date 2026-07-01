import sys
import traceback

with open("c:/Users/vishe/OneDrive/Desktop/Samyak/persona/err_log.txt", "w") as errf:
    try:
        import sqlite3
        import json
        import hashlib
        import os

        db_path = r"c:\Users\vishe\OneDrive\Desktop\Samyak\persona\db.sqlite3"
        out_path = r"c:\Users\vishe\OneDrive\Desktop\Samyak\persona\audio_diag_results.json"

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM AnalysisAPI_individualassessment ORDER BY started_at DESC LIMIT 1")
        assessment = cursor.fetchone()

        if not assessment:
            with open(out_path, "w") as f:
                json.dump({"error": "No assessments found"}, f)
            exit()

        cursor.execute("SELECT * FROM AnalysisAPI_individualassessmentresponse WHERE assessment_id = ? ORDER BY question_order", (assessment['id'],))
        responses = cursor.fetchall()

        results = {
            "assessment_id": assessment['id'],
            "responses": []
        }

        for r in responses:
            ad = json.loads(r['analysis_data']) if r['analysis_data'] else {}
            audio_base64 = ad.get('audio_base64', '')
            
            b64_len = len(audio_base64)
            est_bytes = (b64_len * 3) // 4
            
            full_hash = hashlib.md5(audio_base64.encode('utf-8')).hexdigest() if audio_base64 else None
            
            results["responses"].append({
                "question_order": r['question_order'],
                "b64_len": b64_len,
                "est_bytes": est_bytes,
                "full_hash": full_hash,
                "speech_analysis_status": ad.get('speech_analysis_status'),
                "speech_error": ad.get('speech_analysis', {}).get('error')
            })

        if responses:
            ad = json.loads(responses[0]['analysis_data']) if responses[0]['analysis_data'] else {}
            audio_base64 = ad.get('audio_base64', '')
            if audio_base64:
                if "base64," in audio_base64:
                    audio_base64 = audio_base64.split("base64,")[1]
                import base64
                try:
                    audio_bytes = base64.b64decode(audio_base64)
                    with open(r"c:\Users\vishe\OneDrive\Desktop\Samyak\persona\test_audio_out.webm", "wb") as f:
                        f.write(audio_bytes)
                    results["extracted_audio_size"] = len(audio_bytes)
                except Exception as e:
                    results["extract_error"] = str(e)

        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
            
        errf.write("Success\n")
    except Exception as e:
        errf.write(traceback.format_exc())
