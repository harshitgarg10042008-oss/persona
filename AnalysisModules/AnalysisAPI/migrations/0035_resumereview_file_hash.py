# Generated migration for file_hash field on ResumeReview
# Adds: file_hash (CharField, max_length=64, null=True, blank=True)
# nullable to allow existing records without hash; lazy backfill acceptable

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AnalysisAPI', '0034_individualassessment_cv_analysis_events_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='resumereview',
            name='file_hash',
            field=models.CharField(max_length=64, null=True, blank=True, help_text='SHA-256 hash of resume file bytes for deduplication'),
        ),
    ]
