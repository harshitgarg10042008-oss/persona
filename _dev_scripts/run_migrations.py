import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
import django; django.setup()
from django.core.management import call_command
try:
    with open('migration_status.txt', 'w') as f:
        sys.stdout = f
        call_command('makemigrations', 'AnalysisAPI')
        call_command('migrate')
except Exception as e:
    with open('migration_error.txt', 'w') as f:
        f.write(str(e))
