from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AnalysisAPI', '0016_individualassessment_learning_roadmap'),
    ]

    operations = [
        migrations.AddField(
            model_name='individualassessmentresponse',
            name='star_analysis',
            field=models.JSONField(
                blank=True,
                null=True,
                help_text=(
                    'STAR structure analysis for behavioral responses. '
                    'Schema: {situation: bool, task: bool, action: bool, result: bool, '
                    'score: float 0-10, missing_explanation: str}'
                ),
            ),
        ),
    ]
