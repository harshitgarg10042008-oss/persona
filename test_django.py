import traceback
try:
    import os, sys
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
    django.setup()
    
    from django.core.management import call_command
    with open('django_test_out.txt', 'w') as f:
        f.write("Django setup successful!\n")
except Exception as e:
    with open('django_test_err.txt', 'w') as f:
        f.write(traceback.format_exc())
