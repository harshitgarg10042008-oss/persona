import sys
import traceback
import platform

_outfile = open('test_ml_output.txt', 'w', encoding='utf-8')
def tprint(*args, **kwargs):
    print(*args, **kwargs)
    print(*args, **kwargs, file=_outfile)
    _outfile.flush()

tprint("=== DIAGNOSTIC REPORT ===")

tprint("\n--- 1a. Attire Analyzer ---")
try:
    from AnalysisModules.attire_analyzer import WebAttireAnalyzer
    analyzer1 = WebAttireAnalyzer()
    analyzer1.initialize_models()
    tprint("SUCCESS: Attire Analyzer loaded models successfully.")
except Exception as e:
    tprint("FAILED: Attire Analyzer")
    traceback.print_exc()
    traceback.print_exc(file=_outfile)

tprint("\n--- 1b. Body Language Analyzer ---")
try:
    from AnalysisModules.body_language_analyzer import WebBodyLanguageAnalyzer
    analyzer2 = WebBodyLanguageAnalyzer()
    init_success = analyzer2.initialize_detectors()
    if not init_success:
        tprint("FAILED: Body Language Analyzer (initialize_detectors returned False)")
    else:
        tprint("SUCCESS: Body Language Analyzer loaded models successfully.")
except Exception as e:
    tprint("FAILED: Body Language Analyzer")
    traceback.print_exc()
    traceback.print_exc(file=_outfile)

tprint("\n--- 1c. Speech Analyzer ---")
try:
    from AnalysisModules.speech_analyzer import WebSpeechAnalyzer
    analyzer3 = WebSpeechAnalyzer()
    analyzer3.initialize_models()
    tprint("SUCCESS: Speech Analyzer loaded Whisper and SR successfully.")
except Exception as e:
    tprint("FAILED: Speech Analyzer")
    traceback.print_exc()
    traceback.print_exc(file=_outfile)

