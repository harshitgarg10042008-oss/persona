# Generated migration for ATS fields on ResumeReview
# Adds: ats_score (FloatField, nullable) and ats_feedback (JSONField, default=dict)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AnalysisAPI', '0019_resumereview_recreated'),
    ]

    operations = [
        migrations.AddField(
            model_name='resumereview',
            name='ats_score',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='resumereview',
            name='ats_feedback',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
