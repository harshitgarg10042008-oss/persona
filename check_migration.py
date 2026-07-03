import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
import django; django.setup()
from django.db import connection

# Check if improvement_roadmap column exists
cursor = connection.cursor()
cursor.execute("PRAGMA table_info('analysisapi_individualassessment');")
cols = [row[1] for row in cursor.fetchall()]
print("Columns:", cols)
print("improvement_roadmap present:", 'improvement_roadmap' in cols)
