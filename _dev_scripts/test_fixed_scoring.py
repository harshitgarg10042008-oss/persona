#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisAPI.models import IndividualAssessment
from django.utils import timezone

def test_fixed_scoring():
    # Get assessment 21
    assessment = IndividualAssessment.objects.get(id=21)
    print(f'Assessment ID: {assessment.id}')
    print(f'Before: Speaking={assessment.speaking_score}, Body={assessment.body_language_score}, Attire={assessment.attire_score}, Overall={assessment.overall_score}')

    # Reset scores to trigger recalculation
    assessment.speaking_score = None
    assessment.body_language_score = None  
    assessment.attire_score = None
    assessment.overall_score = None
    
    # Check data structure
    responses = assessment.responses.all()
    snapshots = assessment.snapshots.all()
    
    print(f'\nData Summary:')
    print(f'Responses: {responses.count()}')
    print(f'Snapshots: {snapshots.count()}')
    
    # SPEECH SCORING - Apply the fixed logic
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
            assessment.speaking_score = (total_fluency + total_pronunciation + total_content + total_formality + total_confidence) / (5 * valid_responses)
    
    # VISUAL SCORING - Use overall scores from analyzers
    if snapshots.exists():
        body_language_snapshots = snapshots.filter(analysis_type='body_language')
        attire_snapshots = snapshots.filter(analysis_type='attire')
        
        # Get sample data to check what overall_score analyzers return
        if body_language_snapshots.exists():
            sample_body = body_language_snapshots.first()
            body_overall = sample_body.analysis_data.get('overall_score', 0)
            print(f'Body language overall_score from analyzer: {body_overall}')
            
            # If we have overall scores from analyzers, use them
            if body_overall:
                body_scores = []
                for snapshot in body_language_snapshots:
                    overall_score = snapshot.analysis_data.get('overall_score', 0)
                    if overall_score:
                        # Convert to 0-10 scale
                        if overall_score <= 1:
                            overall_score *= 10
                        body_scores.append(overall_score)
                
                if body_scores:
                    assessment.body_language_score = sum(body_scores) / len(body_scores)
                    print(f'Calculated body language score: {assessment.body_language_score}')
            else:
                print('No overall_score from body language analyzer - setting to 5.0 as placeholder')
                assessment.body_language_score = 5.0
        
        if attire_snapshots.exists():
            sample_attire = attire_snapshots.first()
            attire_overall = sample_attire.analysis_data.get('overall_score', 0)
            print(f'Attire overall_score from analyzer: {attire_overall}')
            
            # If we have overall scores from analyzers, use them
            if attire_overall:
                attire_scores = []
                for snapshot in attire_snapshots:
                    overall_score = snapshot.analysis_data.get('overall_score', 0)
                    if overall_score:
                        # Convert to 0-10 scale
                        if overall_score <= 1:
                            overall_score *= 10
                        attire_scores.append(overall_score)
                
                if attire_scores:
                    assessment.attire_score = sum(attire_scores) / len(attire_scores)
                    print(f'Calculated attire score: {assessment.attire_score}')
            else:
                print('No overall_score from attire analyzer - setting to 7.0 as placeholder')
                assessment.attire_score = 7.0
    
    # Calculate overall score
    scores = [s for s in [
        assessment.speaking_score,
        assessment.body_language_score,
        assessment.attire_score
    ] if s is not None]
    
    if scores:
        assessment.overall_score = sum(scores) / len(scores)
    
    # Save the updated scores
    assessment.save()
    
    print(f'\nFinal Results (0-10 scale):')
    print(f'Speaking: {assessment.speaking_score:.1f}/10')
    print(f'Body Language: {assessment.body_language_score:.1f}/10')
    print(f'Attire: {assessment.attire_score:.1f}/10')
    print(f'Overall: {assessment.overall_score:.1f}/10')

if __name__ == '__main__':
    test_fixed_scoring()