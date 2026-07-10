#!/usr/bin/env python
"""Check current difficulty distribution of PlatformQuestion objects."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisAPI.models import PlatformQuestion
from django.db.models import Count

print(f'Total questions: {PlatformQuestion.objects.count()}')
print(f'Questions with difficulty set: {PlatformQuestion.objects.exclude(difficulty_level__isnull=True).count()}')
print('\nDifficulty distribution:')
for row in PlatformQuestion.objects.values('difficulty_level').annotate(count=Count('id')).order_by('difficulty_level'):
    print(f"  {row['difficulty_level']}: {row['count']}")
