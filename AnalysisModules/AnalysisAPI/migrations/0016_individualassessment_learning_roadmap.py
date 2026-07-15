from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AnalysisAPI', '0015_individualassessment_skill_gap_analysis'),
    ]

    operations = [
        migrations.AddField(
            model_name='individualassessment',
            name='learning_roadmap',
            field=models.JSONField(blank=True, help_text='Structured multi-week learning path from generate_learning_roadmap()', null=True),
        ),
    ]
