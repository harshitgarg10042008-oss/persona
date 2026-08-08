# Generated manually — adds InstitutionDomain table and seat_cap to BusinessUser

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('UserAPI', '0011_individualuser_face_reference_captured_at_and_more'),
    ]

    operations = [
        # ── seat_cap on BusinessUser (join-path seat enforcement) ──────────────
        migrations.AddField(
            model_name='businessuser',
            name='seat_cap',
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text='Maximum number of active student memberships. NULL = unlimited.',
            ),
        ),

        # ── InstitutionDomain table (multi-domain email allowlist) ─────────────
        migrations.CreateModel(
            name='InstitutionDomain',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('domain', models.CharField(
                    max_length=255,
                    help_text='Lowercase email domain without the leading @, e.g. xyzuniversity.edu.in',
                )),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('institution', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='allowed_domains',
                    to='UserAPI.institution',
                )),
            ],
            options={
                'verbose_name': 'Institution Domain',
                'verbose_name_plural': 'Institution Domains',
                'ordering': ['domain'],
                'unique_together': {('institution', 'domain')},
            },
        ),
    ]
