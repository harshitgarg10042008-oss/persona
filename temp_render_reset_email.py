import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from django.template.loader import render_to_string

output = render_to_string(
    'auth/password_reset_email.html',
    {'protocol': 'http', 'domain': 'localhost', 'uid': 'uid', 'token': 'token'}
)
print(output)
