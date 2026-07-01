import sys
import os

out_path = r"c:\Users\vishe\OneDrive\Desktop\Samyak\persona\verify_imports_output.txt"
try:
    sys.path.insert(0, r"c:\Users\vishe\OneDrive\Desktop\Samyak\persona")
    import AnalysisModules as am
    
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"ATTIRE_ANALYSIS_AVAILABLE: {am.ATTIRE_ANALYSIS_AVAILABLE}\n")
        f.write(f"BODY_LANGUAGE_ANALYSIS_AVAILABLE: {am.BODY_LANGUAGE_ANALYSIS_AVAILABLE}\n")
        f.write(f"SPEECH_ANALYSIS_AVAILABLE: {am.SPEECH_ANALYSIS_AVAILABLE}\n")
        f.write("\nFunctions exported:\n")
        for name in am.__all__:
            if hasattr(am, name):
                f.write(f"  {name} -> {type(getattr(am, name)).__name__}\n")
        f.write("\nOK: All imports succeeded\n")
except Exception as e:
    import traceback
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"IMPORT FAILED: {e}\n")
        traceback.print_exc(file=f)
