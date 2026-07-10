import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisModules.AnalysisAPI.models import PlatformQuestion
from django.db.models import Count

print(f'Total questions: {PlatformQuestion.objects.count()}')
print(f'Questions with difficulty: {PlatformQuestion.objects.exclude(difficulty_level__isnull=True).count()}')
print('\nDifficulty distribution:')
dist = PlatformQuestion.objects.values('difficulty_level').annotate(count=Count('id'))
for d in dist:
    print(f"  {d['difficulty_level']}: {d['count']}")
