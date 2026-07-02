#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisAPI.models import IndividualAssessment

def check_analysis_errors():
    # Get assessment 21
    assessment = IndividualAssessment.objects.get(id=21)
    snapshots = assessment.snapshots.all()
    
    body_snapshots = snapshots.filter(analysis_type='body_language')[:5]  # Check first 5
    attire_snapshots = snapshots.filter(analysis_type='attire')[:5]      # Check first 5
    
    print("=== BODY LANGUAGE ANALYSIS ERRORS ===")
    for i, snapshot in enumerate(body_snapshots):
        data = snapshot.analysis_data
        if data:
            if 'error' in data:
                print(f"Body Snapshot {i+1} ERROR: {data['error']}")
            else:
                print(f"Body Snapshot {i+1}: posture={data.get('posture_score')}, eye_contact={data.get('eye_contact_score')}, gesture={data.get('gesture_score')}")
                if data.get('posture_score') == 0:
                    print(f"  - Details: {data.get('details', {}).get('posture', {})}")
        else:
            print(f"Body Snapshot {i+1}: No data")
    
    print("\n=== ATTIRE ANALYSIS ERRORS ===")
    for i, snapshot in enumerate(attire_snapshots):
        data = snapshot.analysis_data
        if data:
            if 'error' in data:
                print(f"Attire Snapshot {i+1} ERROR: {data['error']}")
            else:
                print(f"Attire Snapshot {i+1}: professionalism={data.get('professionalism_score')}, appropriateness={data.get('appropriateness_score')}, grooming={data.get('grooming_score')}")
        else:
            print(f"Attire Snapshot {i+1}: No data")

if __name__ == '__main__':
    check_analysis_errors()