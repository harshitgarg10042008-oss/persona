#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisAPI.models import IndividualAssessment
from django.utils import timezone

def test_scoring():
    # Get assessment 21
    assessment = IndividualAssessment.objects.get(id=21)
    print(f'Assessment ID: {assessment.id}')
    print(f'Before: Speaking={assessment.speaking_score}, Body={assessment.body_language_score}, Attire={assessment.attire_score}, Overall={assessment.overall_score}')

    # Check data structure
    responses = assessment.responses.all()
    snapshots = assessment.snapshots.all()
    
    print(f'\nData Summary:')
    print(f'Responses: {responses.count()}')
    print(f'Snapshots: {snapshots.count()}')
    
    # Sample one response to see speech data structure
    if responses.exists():
        sample_response = responses.first()
        speech_data = sample_response.analysis_data.get('speech_analysis', {})
        print(f'Speech analysis available: {bool(speech_data and not speech_data.get("error"))}')
        if speech_data and not speech_data.get('error'):
            print(f'Sample speech scores: fluency={speech_data.get("fluency_score")}, confidence={speech_data.get("confidence_score")}')
    
    # Sample snapshots to see visual data structure  
    body_snapshots = snapshots.filter(analysis_type='body_language')
    attire_snapshots = snapshots.filter(analysis_type='attire')
    print(f'Body language snapshots: {body_snapshots.count()}')
    print(f'Attire snapshots: {attire_snapshots.count()}')
    
    if body_snapshots.exists():
        sample_body = body_snapshots.first()
        body_data = sample_body.analysis_data
        if body_data and not body_data.get('error'):
            print(f'Sample body language scores: posture={body_data.get("posture_score")}, eye_contact={body_data.get("eye_contact_score")}')
        
    if attire_snapshots.exists():
        sample_attire = attire_snapshots.first()
        attire_data = sample_attire.analysis_data
        if attire_data and not attire_data.get('error'):
            print(f'Sample attire scores: professionalism={attire_data.get("professionalism_score")}, grooming={attire_data.get("grooming_score")}')

    # Now force recalculation by triggering the completion logic
    print(f'\n--- Triggering Score Calculation ---')
    
    # Reset scores  
    assessment.speaking_score = None
    assessment.body_language_score = None  
    assessment.attire_score = None
    assessment.overall_score = None
    
    # Manually trigger the scoring logic from views.py
    if responses.exists():
        # Calculate average speaking scores from analysis_data
        total_fluency = 0
        total_pronunciation = 0
        total_content = 0
        total_formality = 0
        total_confidence = 0
        valid_responses = 0
        
        for response in responses:
            speech_analysis = response.analysis_data.get('speech_analysis', {})
            if speech_analysis and not speech_analysis.get('error'):
                # Speech analyzer returns scores in 0-1 range
                fluency = speech_analysis.get('fluency_score', 0)
                pronunciation = speech_analysis.get('pronunciation_score', 0)
                content = speech_analysis.get('content_score', 0)
                formality = speech_analysis.get('formality_score', 0)  
                confidence = speech_analysis.get('confidence_score', 0)
                
                print(f'Raw scores: fluency={fluency}, pronunciation={pronunciation}, content={content}, formality={formality}, confidence={confidence}')
                
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
            print(f'Calculated speaking score: {assessment.speaking_score}')
    
    if snapshots.exists():
        # Calculate aggregated visual analysis scores
        body_language_snapshots = snapshots.filter(analysis_type='body_language')
        attire_snapshots = snapshots.filter(analysis_type='attire')
        
        # Aggregate body language scores
        total_posture = 0
        total_eye_contact = 0
        total_gesture = 0
        bl_count = 0
        
        for snapshot in body_language_snapshots:
            analysis = snapshot.analysis_data
            if analysis and not analysis.get('error'):
                # Body language analyzer returns scores in 0-1 range
                posture = analysis.get('posture_score', 0)
                eye_contact = analysis.get('eye_contact_score', 0)
                gesture = analysis.get('gesture_score', 0)
                
                print(f'Raw body scores: posture={posture}, eye_contact={eye_contact}, gesture={gesture}')
                
                # Convert to 0-10 scale
                if posture and posture <= 1:
                    posture *= 10
                if eye_contact and eye_contact <= 1:
                    eye_contact *= 10
                if gesture and gesture <= 1:
                    gesture *= 10
                
                total_posture += posture
                total_eye_contact += eye_contact
                total_gesture += gesture
                bl_count += 1
        
        if bl_count > 0:
            assessment.body_language_score = (total_posture + total_eye_contact + total_gesture) / (3 * bl_count)
            print(f'Calculated body language score: {assessment.body_language_score}')
        
        # Aggregate attire scores
        total_professionalism = 0
        total_appropriateness = 0
        total_grooming = 0
        attire_count = 0
        
        for snapshot in attire_snapshots:
            analysis = snapshot.analysis_data
            if analysis and not analysis.get('error'):
                # Attire analyzer returns scores in 0-1 range
                professionalism = analysis.get('professionalism_score', 0)
                appropriateness = analysis.get('appropriateness_score', 0) 
                grooming = analysis.get('grooming_score', 0)
                
                print(f'Raw attire scores: professionalism={professionalism}, appropriateness={appropriateness}, grooming={grooming}')
                
                # Convert to 0-10 scale
                if professionalism and professionalism <= 1:
                    professionalism *= 10
                if appropriateness and appropriateness <= 1:
                    appropriateness *= 10
                if grooming and grooming <= 1:
                    grooming *= 10
                
                total_professionalism += professionalism
                total_appropriateness += appropriateness
                total_grooming += grooming
                attire_count += 1
        
        if attire_count > 0:
            assessment.attire_score = (total_professionalism + total_appropriateness + total_grooming) / (3 * attire_count)
            print(f'Calculated attire score: {assessment.attire_score}')
    
    # Calculate overall score
    scores = [s for s in [
        assessment.speaking_score,
        assessment.body_language_score,
        assessment.attire_score
    ] if s is not None]
    
    if scores:
        assessment.overall_score = sum(scores) / len(scores)
        print(f'Calculated overall score: {assessment.overall_score}')
    
    # Save the updated scores
    assessment.save()
    
    print(f'\nFinal Results:')
    print(f'Speaking: {assessment.speaking_score}')
    print(f'Body Language: {assessment.body_language_score}')
    print(f'Attire: {assessment.attire_score}')
    print(f'Overall: {assessment.overall_score}')

if __name__ == '__main__':
    test_scoring()