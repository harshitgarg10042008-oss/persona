import os
os.system(r'.\venv\Scripts\python.exe manage.py makemigrations AnalysisAPI > migration_output.txt 2>&1')
os.system(r'.\venv\Scripts\python.exe manage.py migrate >> migration_output.txt 2>&1')
