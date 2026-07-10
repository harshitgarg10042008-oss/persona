# Generated migration to normalize difficulty values
from django.db import migrations


def migrate_difficulty_values(apps, schema_editor):
    """Migrate difficulty values from easy/hard to beginner/advanced."""
    PlatformQuestion = apps.get_model('AnalysisAPI', 'PlatformQuestion')
    
    # Migrate 'easy' → 'beginner'
    PlatformQuestion.objects.filter(difficulty_level='easy').update(difficulty_level='beginner')
    
    # Migrate 'hard' → 'advanced'
    PlatformQuestion.objects.filter(difficulty_level='hard').update(difficulty_level='advanced')


class Migration(migrations.Migration):

    dependencies = [
        ('AnalysisAPI', '0011_individualassessment_adaptive_mode_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_difficulty_values, migrations.RunPython.noop),
    ]
