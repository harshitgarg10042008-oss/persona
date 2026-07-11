# Generated manually
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AnalysisAPI', '0012_migrate_difficulty_values'),
    ]

    operations = [
        migrations.AddField(
            model_name='interviewquestion',
            name='difficulty_level',
            field=models.CharField(choices=[('beginner', 'Beginner'), ('intermediate', 'Intermediate'), ('advanced', 'Advanced')], default='intermediate', help_text='Difficulty tier for adaptive selection', max_length=20),
        ),
        migrations.AddField(
            model_name='assessment',
            name='adaptive_mode',
            field=models.BooleanField(default=True, help_text='Whether adaptive difficulty adjustment is enabled. Always ON for Business Assessment.'),
        ),
        migrations.AddField(
            model_name='assessment',
            name='adaptive_path',
            field=models.JSONField(blank=True, default=list, help_text='List of adaptive decisions: [{question_order, previous_difficulty, performance_score, next_difficulty, reason}]'),
        ),
        migrations.AddField(
            model_name='assessment',
            name='current_difficulty',
            field=models.CharField(choices=[('beginner', 'Beginner'), ('intermediate', 'Intermediate'), ('advanced', 'Advanced')], default='intermediate', help_text='Current difficulty tier for adaptive selection', max_length=20),
        ),
    ]
