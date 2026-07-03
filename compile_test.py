import py_compile
import sys
try:
    py_compile.compile('AnalysisModules/AnalysisAPI/views.py', doraise=True)
    print("Syntax OK")
except Exception as e:
    with open('compile_err.txt', 'w') as f:
        f.write(str(e))
