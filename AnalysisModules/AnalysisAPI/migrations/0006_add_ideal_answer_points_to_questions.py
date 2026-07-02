from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AnalysisAPI', '0005_add_business_assessment_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='platformquestion',
            name='ideal_answer_points',
            field=models.TextField(blank=True, null=True, help_text='Optional key points a strong answer should cover'),
        ),
        migrations.AddField(
            model_name='interviewquestion',
            name='ideal_answer_points',
            field=models.TextField(blank=True, null=True, help_text='Optional key points a strong answer should cover'),
        ),
    ]
