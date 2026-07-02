#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisAPI.models import IndividualAssessment

# Restore the individual scores
latest = IndividualAssessment.objects.get(session_id='0a9ec4c0-7975-4e72-b50f-7ec49645223c')

# Set the correct individual scores (from our earlier calculation)
latest.speaking_score = 6.7
latest.body_language_score = 6.0
latest.attire_score = 8.0

# Calculate the proper overall score (not out of 100, just 0-10)
overall = (6.7 + 6.0 + 8.0) / 3
latest.overall_score = overall

latest.save()
print(f'Restored scores: Speaking={latest.speaking_score}, Body={latest.body_language_score}, Attire={latest.attire_score}, Overall={latest.overall_score}')