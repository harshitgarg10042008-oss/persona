import re
with open(r'c:\Users\vishe\OneDrive\Desktop\Samyak\persona\AnalysisModules\AnalysisAPI\views.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if 'business_assessment_complete' in line:
        print(f"Line {i+1}: {line.strip()}")
