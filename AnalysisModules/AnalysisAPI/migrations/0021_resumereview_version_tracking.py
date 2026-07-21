# Generated migration for version_number field on ResumeReview
# Adds: version_number (PositiveIntegerField, default=1)
# default=1 means all existing rows are safely backfilled without touching the DB manually.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AnalysisAPI', '0020_resumereview_ats_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='resumereview',
            name='version_number',
            field=models.PositiveIntegerField(default=1),
        ),
    ]
