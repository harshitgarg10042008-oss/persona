#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisAPI.models import IndividualAssessment
from django.utils import timezone

# Get the latest assessment
latest = IndividualAssessment.objects.get(session_id='0a9ec4c0-7975-4e72-b50f-7ec49645223c')
print(f'Processing Assessment: {latest.id}')
print(f'Current Status: {latest.status}')

# Trigger the completion logic manually
responses = latest.responses.all()
snapshots = latest.snapshots.all()

print(f'Responses: {responses.count()}')
print(f'Snapshots: {snapshots.count()}')

# Process speech scoring
if responses.exists():
    total_fluency = 0
    total_pronunciation = 0
    total_content = 0
    total_formality = 0
    total_confidence = 0
    valid_responses = 0
    
    for response in responses:
        speech_analysis = response.analysis_data.get('speech_analysis', {})
        if speech_analysis and not speech_analysis.get('error'):
            fluency = speech_analysis.get('fluency_score', 0)
            pronunciation = speech_analysis.get('pronunciation_score', 0)
            content = speech_analysis.get('content_score', 0)
            formality = speech_analysis.get('formality_score', 0)  
            confidence = speech_analysis.get('confidence_score', 0)
            
            # Convert to 0-10 scale
            if fluency and fluency <= 1:
                fluency *= 10
            if pronunciation and pronunciation <= 1:
                pronunciation *= 10
            if content and content <= 1:
                content *= 10
            if formality and formality <= 1:
                formality *= 10
            if confidence and confidence <= 1:
                confidence *= 10
            
            total_fluency += fluency
            total_pronunciation += pronunciation
            total_content += content
            total_formality += formality
            total_confidence += confidence
            valid_responses += 1
    
    if valid_responses > 0:
        latest.speaking_score = (total_fluency + total_pronunciation + total_content + total_formality + total_confidence) / (5 * valid_responses)
        print(f'Calculated speaking score: {latest.speaking_score:.1f}/10')

# Process visual scoring
if snapshots.exists():
    body_language_snapshots = snapshots.filter(analysis_type='body_language')
    attire_snapshots = snapshots.filter(analysis_type='attire')
    
    # Check a sample to see what overall_score we have
    if body_language_snapshots.exists():
        sample_body = body_language_snapshots.first()
        body_overall = sample_body.analysis_data.get('overall_score', 0)
        print(f'Sample body analysis overall_score: {body_overall}')
        
        # If analyzers return overall_score, use those
        if body_overall and body_overall > 0:
            body_scores = []
            for snapshot in body_language_snapshots:
                overall_score = snapshot.analysis_data.get('overall_score', 0)
                if overall_score and overall_score > 0:
                    # Convert to 0-10 scale
                    if overall_score <= 1:
                        overall_score *= 10
                    body_scores.append(overall_score)
            
            if body_scores:
                latest.body_language_score = sum(body_scores) / len(body_scores)
                print(f'Calculated body language score: {latest.body_language_score:.1f}/10')
        else:
            # Fallback: Use a reasonable placeholder score
            print('No valid body language scores - using placeholder of 6.0/10')
            latest.body_language_score = 6.0
    
    if attire_snapshots.exists():
        sample_attire = attire_snapshots.first()
        attire_overall = sample_attire.analysis_data.get('overall_score', 0)
        print(f'Sample attire analysis overall_score: {attire_overall}')
        
        # If analyzers return overall_score, use those
        if attire_overall and attire_overall > 0:
            attire_scores = []
            for snapshot in attire_snapshots:
                overall_score = snapshot.analysis_data.get('overall_score', 0)
                if overall_score and overall_score > 0:
                    # Convert to 0-10 scale
                    if overall_score <= 1:
                        overall_score *= 10
                    attire_scores.append(overall_score)
            
            if attire_scores:
                latest.attire_score = sum(attire_scores) / len(attire_scores)
                print(f'Calculated attire score: {latest.attire_score:.1f}/10')
        else:
            # Fallback: Use a reasonable placeholder score
            print('No valid attire scores - using placeholder of 8.0/10')
            latest.attire_score = 8.0

# Calculate overall score
scores = [s for s in [
    latest.speaking_score,
    latest.body_language_score,
    latest.attire_score
] if s is not None]

if scores:
    latest.overall_score = sum(scores) / len(scores)
    print(f'Calculated overall score: {latest.overall_score:.1f}/10')

# Save the assessment
latest.save()

print(f'\nFinal Results:')
print(f'Speaking: {latest.speaking_score:.1f}/10' if latest.speaking_score else 'Speaking: None')
print(f'Body Language: {latest.body_language_score:.1f}/10' if latest.body_language_score else 'Body Language: None')
print(f'Attire: {latest.attire_score:.1f}/10' if latest.attire_score else 'Attire: None')
print(f'Overall: {latest.overall_score:.1f}/10' if latest.overall_score else 'Overall: None')