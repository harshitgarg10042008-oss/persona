import base64
from .models import IndividualAssessmentResponse

try:
    from AnalysisModules import analyze_speech
except ImportError:
    def analyze_speech(*args, **kwargs):
        return {"error": "Speech analysis not available"}

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
        # Decode audio data
        audio_bytes = base64.b64decode(audio_data)
        
        # Analyze speech
        speech_analysis = analyze_speech(audio_bytes, question_text)
        
        # Convert numpy types to native Python types for JSON serialization
        def convert_numpy_types(obj):
            if hasattr(obj, 'item'):  # numpy scalar
                return obj.item()
            elif hasattr(obj, 'tolist'):  # numpy array
                return obj.tolist()
            elif isinstance(obj, dict):
                return {key: convert_numpy_types(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [convert_numpy_types(item) for item in obj]
            return obj
        
        # Clean the analysis results
        cleaned_analysis = convert_numpy_types(speech_analysis)
        
        # Update response with analysis
        # Using dict unpacking or copy might be safer if analysis_data isn't mutating well, 
        # but the original code did `response.analysis_data['speech_analysis'] = ...`
        # We should assign a new dict to ensure Django JSONField detects the change if it's an older version,
        # but direct assignment usually works in modern Django.
        
        analysis_data = response.analysis_data or {}
        analysis_data['speech_analysis'] = cleaned_analysis
        analysis_data['speech_analysis_status'] = 'completed'
        response.analysis_data = analysis_data
        response.save()
        print(f"Speech analysis for response {response_id} completed successfully.")
        
    except Exception as e:
        print(f"Speech analysis failed for response {response_id}: {e}")
        analysis_data = response.analysis_data or {}
        analysis_data['speech_analysis'] = {"error": str(e)}
        analysis_data['speech_analysis_status'] = 'failed'
        response.analysis_data = analysis_data
        response.save()
