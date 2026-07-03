import sys
import os
import io
import traceback
from django.core.management import call_command

log_file = open("roadmap_debug.txt", "w")
sys.stdout = log_file
sys.stderr = log_file

try:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
    import django
    django.setup()
    
    call_command('verify_roadmap')
except Exception as e:
    print("EXCEPTION OCCURRED:", e)
    traceback.print_exc()
finally:
    log_file.close()
