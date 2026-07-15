from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AnalysisAPI', '0017_individualassessmentresponse_star_analysis'),
    ]

    operations = [
        migrations.AddField(
            model_name='individualassessment',
            name='communication_analysis',
            field=models.JSONField(
                blank=True,
                null=True,
                help_text=(
                    'Communication style analysis from generate_communication_analysis(). '
                    'Schema: {summary: str, traits: [{label: str, explanation: str}, ...]}'
                ),
            ),
        ),
    ]
