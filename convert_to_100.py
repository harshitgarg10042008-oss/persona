#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisAPI.models import IndividualAssessment

latest = IndividualAssessment.objects.get(session_id='0a9ec4c0-7975-4e72-b50f-7ec49645223c')
print(f'Before: Speaking={latest.speaking_score}, Body={latest.body_language_score}, Attire={latest.attire_score}, Overall={latest.overall_score}')

# Convert to 0-100 scale
if latest.speaking_score:
    latest.speaking_score *= 10
if latest.body_language_score:
    latest.body_language_score *= 10
if latest.attire_score:
    latest.attire_score *= 10
if latest.overall_score:
    latest.overall_score *= 10

latest.save()
print(f'After: Speaking={latest.speaking_score}/100, Body={latest.body_language_score}/100, Attire={latest.attire_score}/100, Overall={latest.overall_score}/100')