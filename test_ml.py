import sys
import traceback
import platform

print("=== DIAGNOSTIC REPORT ===")

print("\n--- 1a. Attire Analyzer ---")
try:
    from AnalysisModules.attire_analyzer import WebAttireAnalyzer
    analyzer1 = WebAttireAnalyzer()
    analyzer1.initialize_models()
    print("SUCCESS: Attire Analyzer loaded models successfully.")
except Exception as e:
    print("FAILED: Attire Analyzer")
    traceback.print_exc()

print("\n--- 1b. Body Language Analyzer ---")
try:
    from AnalysisModules.body_language_analyzer import WebBodyLanguageAnalyzer
    analyzer2 = WebBodyLanguageAnalyzer()
    init_success = analyzer2.initialize_detectors()
    if not init_success:
        print("FAILED: Body Language Analyzer (initialize_detectors returned False)")
    else:
        print("SUCCESS: Body Language Analyzer loaded models successfully.")
except Exception as e:
    print("FAILED: Body Language Analyzer")
    traceback.print_exc()

print("\n--- 1c. Speech Analyzer ---")
try:
    from AnalysisModules.speech_analyzer import WebSpeechAnalyzer
    analyzer3 = WebSpeechAnalyzer()
    analyzer3.initialize_models()
    print("SUCCESS: Speech Analyzer loaded Whisper and SR successfully.")
except Exception as e:
    print("FAILED: Speech Analyzer")
    traceback.print_exc()
