import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisAPI.models import PlatformQuestion, PlatformJobTitle

print('Total Questions:', PlatformQuestion.objects.count())
roles = PlatformJobTitle.objects.all()
for r in roles:
    total = r.questions.count()
    mand = r.questions.filter(is_mandatory=True).count()
    opt = r.questions.filter(is_mandatory=False).count()
    print(f'{r.title}: {total} total, {mand} mandatory, {opt} optional')
