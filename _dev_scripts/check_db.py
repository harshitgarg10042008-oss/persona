import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
import django; django.setup()
from django.db import connection
cursor = connection.cursor()
cursor.execute("PRAGMA table_info('AnalysisAPI_individualassessment');")
rows = cursor.fetchall()
with open('db_out.txt', 'w') as f:
    for r in rows:
        f.write(str(r) + '\n')
