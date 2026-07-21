"""
Migration 0022: Add CoverLetter model

New table: AnalysisAPI_coverletter
Depends on: AnalysisAPI 0021, UserAPI (CustomUser)
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AnalysisAPI', '0021_resumereview_version_tracking'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CoverLetter',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('job_title', models.CharField(max_length=255)),
                ('company_name', models.CharField(blank=True, max_length=255)),
                ('job_description', models.TextField(blank=True)),
                ('generated_text', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='cover_letters',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('resume_review', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='cover_letters',
                    to='AnalysisAPI.resumereview',
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
