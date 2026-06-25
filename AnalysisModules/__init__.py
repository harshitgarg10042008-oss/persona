"""
AnalysisModules package
Web-optimized AI analysis modules for Persona assessment system
"""

# Import main analysis functions for easy access
try:
    from .attire_analyzer import analyze_attire, analyze_attire_base64
    from .body_language_analyzer import analyze_body_language, analyze_body_language_base64
    
    # Speech analyzer imports may fail if dependencies not installed
    try:
        from .speech_analyzer import analyze_speech, quick_transcribe
        SPEECH_ANALYSIS_AVAILABLE = True
    except ImportError as e:
        print(f"Speech analysis not available: {e}")
        SPEECH_ANALYSIS_AVAILABLE = False
        
        # Provide fallback functions
        def analyze_speech(*args, **kwargs):
            return {"error": "Speech analysis dependencies not installed"}
        
        def quick_transcribe(*args, **kwargs):
            return "Speech analysis not available"
    
    ATTIRE_ANALYSIS_AVAILABLE = True
    BODY_LANGUAGE_ANALYSIS_AVAILABLE = True
    
except ImportError as e:
    print(f"Analysis modules not fully available: {e}")
    
    # Provide fallback functions
    def analyze_attire(*args, **kwargs):
        return {"error": "Attire analysis dependencies not installed"}
    
    def analyze_attire_base64(*args, **kwargs):
        return {"error": "Attire analysis dependencies not installed"}
    
    def analyze_body_language(*args, **kwargs):
        return {"error": "Body language analysis dependencies not installed"}
    
    def analyze_body_language_base64(*args, **kwargs):
        return {"error": "Body language analysis dependencies not installed"}
    
    def analyze_speech(*args, **kwargs):
        return {"error": "Speech analysis dependencies not installed"}
    
    def quick_transcribe(*args, **kwargs):
        return "Analysis not available"
    
    ATTIRE_ANALYSIS_AVAILABLE = False
    BODY_LANGUAGE_ANALYSIS_AVAILABLE = False
    SPEECH_ANALYSIS_AVAILABLE = False

# Module information
__version__ = "1.0.0"
__author__ = "Persona Assessment System"

# Export analysis availability flags
__all__ = [
    'analyze_attire',
    'analyze_attire_base64', 
    'analyze_body_language',
    'analyze_body_language_base64',
    'analyze_speech',
    'quick_transcribe',
    'ATTIRE_ANALYSIS_AVAILABLE',
    'BODY_LANGUAGE_ANALYSIS_AVAILABLE', 
    'SPEECH_ANALYSIS_AVAILABLE'
]