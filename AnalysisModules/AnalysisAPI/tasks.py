import base64
import hashlib
from .models import IndividualAssessmentResponse
from AnalysisModules.feedback_generator import evaluate_answer_content

try:
    from AnalysisModules import analyze_speech
except ImportError:
    def analyze_speech(*args, **kwargs):
        return {"error": "Speech analysis not available"}


def _decode_audio_base64(audio_data: str) -> bytes:
    """Decode base64 audio, stripping a data-URL prefix when present."""
    if not audio_data:
        return b''
    raw = audio_data.strip()
    if raw.startswith('data:') and ',' in raw:
        raw = raw.split(',', 1)[1]
    return base64.b64decode(raw)


def run_speech_analysis_task(response_id, audio_data, question_text):
    """
    Background task to analyze speech and update the assessment response.
    """
    try:
        response = IndividualAssessmentResponse.objects.get(id=response_id)
    except IndividualAssessmentResponse.DoesNotExist:
        print(f"Task failed: Response {response_id} not found.")
        return

    try:
        audio_bytes = _decode_audio_base64(audio_data)
        audio_hash = hashlib.md5(audio_bytes).hexdigest()

        analysis_data = response.analysis_data or {}
        analysis_data['debug_audio'] = {
            'base64_len': len(audio_data),
            'bytes_len': len(audio_bytes),
            'hash': audio_hash,
        }

        if len(audio_bytes) < 1024:
            analysis_data['speech_analysis'] = {
                'error': f'Audio too small ({len(audio_bytes)} bytes) — recording likely empty',
                'transcription': '',
                'word_count': 0,
            }
            analysis_data['speech_analysis_status'] = 'completed'
            response.analysis_data = analysis_data
            response.save()
            print(f"Speech analysis skipped for response {response_id}: audio only {len(audio_bytes)} bytes")
            return

        speech_analysis = analyze_speech(audio_bytes, question_text)

        def convert_numpy_types(obj):
            if hasattr(obj, 'item'):
                return obj.item()
            elif hasattr(obj, 'tolist'):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {key: convert_numpy_types(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [convert_numpy_types(item) for item in obj]
            return obj

        cleaned_analysis = convert_numpy_types(speech_analysis)

        speech_transcript = cleaned_analysis.get('transcription', '') or ''
        ideal_answer_points = getattr(response.question, 'ideal_answer_points', None)
        content_evaluation = evaluate_answer_content(
            question_text=response.question.question_text,
            transcript=speech_transcript,
            ideal_answer_points=ideal_answer_points,
        )

        analysis_data['speech_analysis'] = cleaned_analysis
        analysis_data['content_evaluation'] = content_evaluation
        analysis_data['speech_analysis_status'] = 'completed'
        response.analysis_data = analysis_data
        response.save()
        print(f"Speech analysis for response {response_id} completed successfully ({len(audio_bytes)} bytes).")

    except Exception as e:
        print(f"Speech analysis failed for response {response_id}: {e}")
        analysis_data = response.analysis_data or {}
        analysis_data['speech_analysis'] = {"error": str(e)}
        analysis_data['speech_analysis_status'] = 'failed'
        response.analysis_data = analysis_data
        response.save()
