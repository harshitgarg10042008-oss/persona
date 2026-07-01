"""
AnalysisModules package
Web-optimized AI analysis modules for Persona assessment system
"""

# --- Attire analyzer (independent) ---
try:
    from .attire_analyzer import analyze_attire, analyze_attire_base64
    ATTIRE_ANALYSIS_AVAILABLE = True
except ImportError as e:
    import logging as _logging
    _logging.getLogger(__name__).warning(f"Attire analysis not available: {e}")
    ATTIRE_ANALYSIS_AVAILABLE = False

    def analyze_attire(*args, **kwargs):
        return {"error": "Attire analysis dependencies not installed"}

    def analyze_attire_base64(*args, **kwargs):
        return {"error": "Attire analysis dependencies not installed"}

# --- Body language analyzer (independent) ---
try:
    from .body_language_analyzer import analyze_body_language, analyze_body_language_base64
    BODY_LANGUAGE_ANALYSIS_AVAILABLE = True
except ImportError as e:
    import logging as _logging
    _logging.getLogger(__name__).warning(f"Body language analysis not available: {e}")
    BODY_LANGUAGE_ANALYSIS_AVAILABLE = False

    def analyze_body_language(*args, **kwargs):
        return {"error": "Body language analysis dependencies not installed"}

    def analyze_body_language_base64(*args, **kwargs):
        return {"error": "Body language analysis dependencies not installed"}

# --- Speech analyzer (independent) ---
try:
    from .speech_analyzer import analyze_speech, quick_transcribe
    SPEECH_ANALYSIS_AVAILABLE = True
except ImportError as e:
    import logging as _logging
    _logging.getLogger(__name__).warning(f"Speech analysis not available: {e}")
    SPEECH_ANALYSIS_AVAILABLE = False

    def analyze_speech(*args, **kwargs):
        return {"error": "Speech analysis dependencies not installed"}

    def quick_transcribe(*args, **kwargs):
        return "Speech analysis not available"


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