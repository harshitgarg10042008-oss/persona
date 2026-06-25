#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisAPI.models import IndividualAssessment

# Get the latest assessment
latest = IndividualAssessment.objects.filter(status='completed').order_by('-completed_at').first()
if latest:
    print(f'Latest Assessment: {latest.id}')
    print(f'Session ID: {latest.session_id}')
    print(f'Speaking: {latest.speaking_score:.1f}/10' if latest.speaking_score else 'Speaking: None')
    print(f'Body Language: {latest.body_language_score:.1f}/10' if latest.body_language_score else 'Body Language: None')
    print(f'Attire: {latest.attire_score:.1f}/10' if latest.attire_score else 'Attire: None')
    print(f'Overall: {latest.overall_score:.1f}/10' if latest.overall_score else 'Overall: None')
    
    # Check snapshot scores
    snapshots = latest.snapshots.all()
    body_snapshots = snapshots.filter(analysis_type='body_language')
    attire_snapshots = snapshots.filter(analysis_type='attire')
    
    print(f'\nSnapshot Summary:')
    print(f'Total snapshots: {snapshots.count()}')
    print(f'Body language snapshots: {body_snapshots.count()}')
    print(f'Attire snapshots: {attire_snapshots.count()}')
    
    if body_snapshots.exists():
        body_scores = [s.score for s in body_snapshots if s.score and s.score > 0]
        print(f'Valid body scores: {len(body_scores)} out of {body_snapshots.count()}')
        if body_scores:
            print(f'Body score range: {min(body_scores):.1f} - {max(body_scores):.1f}')
            print(f'Sample body scores: {body_scores[:5]}')
    
    if attire_snapshots.exists():
        attire_scores = [s.score for s in attire_snapshots if s.score and s.score > 0]
        print(f'Valid attire scores: {len(attire_scores)} out of {attire_snapshots.count()}')
        if attire_scores:
            print(f'Attire score range: {min(attire_scores):.1f} - {max(attire_scores):.1f}')
            print(f'Sample attire scores: {attire_scores[:5]}')
else:
    print('No completed assessments found')