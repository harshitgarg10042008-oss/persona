#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisAPI.models import IndividualAssessment

# Fix the current assessment
latest = IndividualAssessment.objects.get(session_id='0a9ec4c0-7975-4e72-b50f-7ec49645223c')
print(f'Current scores: Speaking={latest.speaking_score}, Body={latest.body_language_score}, Attire={latest.attire_score}, Overall={latest.overall_score}')

# Calculate the correct single score
# The previous scores were: Speaking=6.7/10, Body=6.0/10, Attire=8.0/10
# This should be: (6.7 + 6.0 + 8.0) / 3 = 6.9/10 = 69/100

correct_overall_score = 69.0

# Set ONLY the overall score
latest.overall_score = correct_overall_score
latest.speaking_score = None
latest.body_language_score = None  
latest.attire_score = None

latest.save()
print(f'Fixed to single score: {latest.overall_score}/100')