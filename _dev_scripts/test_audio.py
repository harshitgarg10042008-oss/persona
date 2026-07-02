import os
import django
import sys
import json
import base64
import tempfile
import subprocess
import traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisAPI.models import IndividualAssessment
from AnalysisModules.speech_analyzer import WebSpeechAnalyzer

try:
    assessment = IndividualAssessment.objects.order_by('-started_at').first()
    responses = assessment.responses.all()
    if not responses:
        print("No responses found.")
        sys.exit(0)
        
    r = responses.first()
    analysis_data = r.analysis_data
    
    if 'audio_base64' in analysis_data:
        audio_b64 = analysis_data['audio_base64']
        audio_bytes = base64.b64decode(audio_b64)
        
        print(f"--- Audio for Response Q{r.question_order} ---")
        temp_audio_path = os.path.join(os.getcwd(), 'test_audio.webm')
        with open(temp_audio_path, 'wb') as f:
            f.write(audio_bytes)
            
        file_size = os.path.getsize(temp_audio_path)
        print(f"Saved test_audio.webm (Size: {file_size} bytes)")
        
        try:
            print("\n--- ffprobe output ---")
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_format', '-show_streams', temp_audio_path],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(result.stdout)
            else:
                print(f"ffprobe failed: {result.stderr}")
        except Exception as e:
            print(f"ffprobe error: {e}")
                
        print("\n--- Whisper direct test ---")
        analyzer = WebSpeechAnalyzer()
        analyzer.initialize_models()
        
        try:
            result = analyzer.whisper_model.transcribe(temp_audio_path)
            print("Whisper Result:")
            # Print only text and a few segments to not overflow
            out = {
                'text': result.get('text'),
                'segments': result.get('segments', [])[:2] # first 2 segments
            }
            print(json.dumps(out, indent=2, default=str))
        except Exception as e:
            print(f"Whisper transcription error:\n{traceback.format_exc()}")
            
    else:
        print("No audio_base64 found in response analysis_data.")
        
except Exception as e:
    print(f"Script Error:\n{traceback.format_exc()}")
