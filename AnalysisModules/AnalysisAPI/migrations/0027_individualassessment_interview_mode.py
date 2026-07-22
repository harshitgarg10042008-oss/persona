# Generated manually
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AnalysisAPI', '0025_interviewsummaryvideo_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='individualassessment',
            name='interview_mode',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('hr', 'HR'),
                    ('technical', 'Technical'),
                ],
                default='hr',
                help_text='Interview style/mode for this assessment'
            ),
        ),
    ]
