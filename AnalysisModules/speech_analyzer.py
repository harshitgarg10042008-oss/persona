"""
Web-optimized speech analysis module for Django backend
Analyzes speech fluency, pronunciation, and content relevance
"""

import logging
import numpy as np
import librosa
import io
import wave
import json
from typing import Dict, List, Tuple, Optional
import tempfile
import os
import re
from datetime import datetime
import whisper
import speech_recognition as sr
from textblob import TextBlob
import nltk
from collections import Counter

# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt_tab')

try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize, sent_tokenize

logger = logging.getLogger(__name__)

class WebSpeechAnalyzer:
    """Web-optimized speech analyzer for Django assessment system"""
    
    def __init__(self):
        self.whisper_model = None
        self.sr_recognizer = None
        self.is_initialized = False
        
        # Analysis configuration
        self.analysis_config = {
            'fluency_weight': 0.25,
            'pronunciation_weight': 0.20,
            'content_weight': 0.25,
            'formality_weight': 0.15,
            'confidence_weight': 0.15,
            
            # Fluency thresholds
            'min_words_per_minute': 120,
            'max_words_per_minute': 180,
            'optimal_pause_duration': 0.5,
            'max_pause_duration': 3.0,
            
            # Content analysis
            'min_response_length': 10,  # words
            'optimal_response_length': 50,  # words
        }
        
        # Professional vocabulary and phrases
        self.professional_vocabulary = {
            'positive_indicators': [
                'experience', 'skills', 'responsible', 'achievements', 'goals',
                'leadership', 'teamwork', 'collaboration', 'innovation', 'problem-solving',
                'analytical', 'strategic', 'efficient', 'dedicated', 'professional',
                'successful', 'accomplished', 'motivated', 'passionate', 'expertise'
            ],
            'filler_words': [
                'um', 'uh', 'like', 'you know', 'basically', 'actually', 'literally',
                'sort of', 'kind of', 'i mean', 'so', 'well', 'right'
            ],
            'informal_words': [
                'yeah', 'yep', 'nope', 'gonna', 'wanna', 'gotta', 'kinda', 'sorta',
                'totally', 'awesome', 'cool', 'stuff', 'things', 'guys'
            ]
        }
    
    def initialize_models(self):
        """Initialize speech recognition models - call once when needed"""
        try:
            if self.is_initialized:
                return True
                
            logger.info("Initializing speech analysis models...")
            
            # Initialize Whisper for transcription
            self.whisper_model = whisper.load_model("base")
            
            # Initialize SpeechRecognition
            self.sr_recognizer = sr.Recognizer()
            
            self.is_initialized = True
            logger.info("Speech analysis models initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize speech models: {e}")
            return False
    
    def analyze_audio(self, audio_data: bytes, question_text: str = "", response_duration: float = None) -> Dict:
        """
        Main analysis function for web use
        
        Args:
            audio_data: Raw audio bytes (WAV format preferred)
            question_text: The question that was asked
            response_duration: Duration of response in seconds
            
        Returns:
            Dict with analysis results and scores
        """
        try:
            if not self.is_initialized:
                if not self.initialize_models():
                    return self._error_result("Failed to initialize speech models")
            
            # Initialize results structure
            results = {
                'overall_score': 0.0,
                'fluency_score': 0.0,
                'pronunciation_score': 0.0,
                'content_score': 0.0,
                'formality_score': 0.0,
                'confidence_score': 0.0,
                'transcription': '',
                'word_count': 0,
                'speaking_rate': 0.0,
                'details': {},
                'feedback': [],
                'recommendations': [],
                'analysis_confidence': 0.0,
                'timestamp': datetime.now().isoformat()
            }
            
            # Save audio to temporary file for processing
            # IMPORTANT: use .webm suffix because the browser records audio/webm;codecs=opus.
            # ffmpeg (used by Whisper) relies on the file extension to identify the container
            # format. If the extension is .wav but the bytes are WebM, ffmpeg decodes silence
            # and Whisper returns an empty transcription → "No speech detected".
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_audio_path = temp_file.name
            
            try:
                # Transcribe audio
                transcription_results = self._transcribe_audio(temp_audio_path)
                results['transcription'] = transcription_results['text']
                results['word_count'] = transcription_results['word_count']
                results['details']['transcription'] = transcription_results
                
                if results['word_count'] == 0:
                    return self._error_result("No speech detected in audio")
                
                # Analyze audio features
                audio_features = self._analyze_audio_features(temp_audio_path, response_duration)
                results['speaking_rate'] = audio_features['speaking_rate']
                results['details']['audio_features'] = audio_features
                
                # Analyze fluency
                fluency_results = self._analyze_fluency(results['transcription'], audio_features)
                results['fluency_score'] = fluency_results['score']
                results['details']['fluency'] = fluency_results
                
                # Analyze pronunciation (basic metrics)
                pronunciation_results = self._analyze_pronunciation(audio_features, transcription_results)
                results['pronunciation_score'] = pronunciation_results['score']
                results['details']['pronunciation'] = pronunciation_results
                
                # Analyze content relevance and quality
                content_results = self._analyze_content(results['transcription'], question_text)
                results['content_score'] = content_results['score']
                results['details']['content'] = content_results
                
                # Analyze formality and professionalism
                formality_results = self._analyze_formality(results['transcription'])
                results['formality_score'] = formality_results['score']
                results['details']['formality'] = formality_results
                
                # Calculate confidence score
                confidence_results = self._analyze_confidence(results['transcription'], audio_features)
                results['confidence_score'] = confidence_results['score']
                results['details']['confidence'] = confidence_results
                
                # Calculate overall analysis confidence
                results['analysis_confidence'] = self._calculate_analysis_confidence(results['details'])
                
                # Generate feedback and recommendations
                self._generate_feedback(results)
                
                # Calculate overall score
                results['overall_score'] = self._calculate_overall_score(results)
                
                return results
                
            finally:
                # Clean up temporary file
                if os.path.exists(temp_audio_path):
                    os.unlink(temp_audio_path)
            
        except Exception as e:
            logger.error(f"Error in speech analysis: {e}")
            return self._error_result(str(e))
    
    def _transcribe_audio(self, audio_path: str) -> Dict:
        """Transcribe audio using Whisper"""
        try:
            result = self.whisper_model.transcribe(audio_path)
            text = result['text'].strip()
            
            # Basic word counting
            words = word_tokenize(text.lower())
            word_count = len([word for word in words if word.isalpha()])
            
            return {
                'text': text,
                'word_count': word_count,
                'language': result.get('language', 'en'),
                'segments': result.get('segments', []),
                'confidence': getattr(result, 'avg_logprob', 0.5)
            }
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return {
                'text': '',
                'word_count': 0,
                'error': str(e)
            }
    
    def _analyze_audio_features(self, audio_path: str, response_duration: float = None) -> Dict:
        """Analyze audio features using librosa"""
        try:
            # Load audio
            y, sr = librosa.load(audio_path, sr=None)
            duration = len(y) / sr
            
            # Extract features
            features = {}
            
            # Speaking rate
            onset_frames = librosa.onset.onset_detect(y=y, sr=sr)
            onset_times = librosa.onset.onset_strength(y=y, sr=sr)
            features['onset_count'] = len(onset_frames)
            features['speaking_rate'] = len(onset_frames) / duration if duration > 0 else 0
            
            # Pitch analysis
            pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
            pitch_values = []
            for frame in range(pitches.shape[1]):
                index = magnitudes[:, frame].argmax()
                pitch = pitches[index, frame]
                if pitch > 0:
                    pitch_values.append(pitch)
            
            if pitch_values:
                features['avg_pitch'] = np.mean(pitch_values)
                features['pitch_variance'] = np.var(pitch_values)
                features['pitch_range'] = max(pitch_values) - min(pitch_values)
            else:
                features['avg_pitch'] = 0
                features['pitch_variance'] = 0
                features['pitch_range'] = 0
            
            # Energy and volume
            rms = librosa.feature.rms(y=y)[0]
            features['avg_energy'] = np.mean(rms)
            features['energy_variance'] = np.var(rms)
            
            # Spectral features
            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            features['avg_spectral_centroid'] = np.mean(spectral_centroids)
            
            # Pause analysis
            features['duration'] = duration
            features['silence_ratio'] = self._calculate_silence_ratio(y, sr)
            
            return features
            
        except Exception as e:
            logger.error(f"Audio feature analysis failed: {e}")
            return {'error': str(e), 'duration': 0, 'speaking_rate': 0}
    
    def _calculate_silence_ratio(self, y, sr, threshold=0.01):
        """Calculate ratio of silence in audio"""
        try:
            # Simple silence detection based on RMS energy
            rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
            silence_frames = np.sum(rms < threshold)
            total_frames = len(rms)
            return silence_frames / total_frames if total_frames > 0 else 0
        except:
            return 0.5  # Default value
    
    def _analyze_fluency(self, text: str, audio_features: Dict) -> Dict:
        """Analyze speech fluency"""
        try:
            words = word_tokenize(text.lower())
            word_count = len([word for word in words if word.isalpha()])
            
            # Calculate words per minute
            duration = audio_features.get('duration', 1)
            wpm = (word_count / duration) * 60 if duration > 0 else 0
            
            # Score based on optimal speaking rate
            config = self.analysis_config
            if config['min_words_per_minute'] <= wpm <= config['max_words_per_minute']:
                rate_score = 1.0
            else:
                deviation = min(
                    abs(wpm - config['min_words_per_minute']),
                    abs(wpm - config['max_words_per_minute'])
                )
                rate_score = max(0, 1 - (deviation / 50))  # 50 WPM tolerance
            
            # Analyze pauses (silence ratio)
            silence_ratio = audio_features.get('silence_ratio', 0.3)
            pause_score = 1 - abs(silence_ratio - 0.2) * 2  # Optimal around 20% silence
            pause_score = max(0, min(pause_score, 1))
            
            # Detect filler words
            filler_count = sum(1 for word in words if word in self.professional_vocabulary['filler_words'])
            filler_ratio = filler_count / word_count if word_count > 0 else 0
            filler_score = max(0, 1 - (filler_ratio * 5))  # Penalize excessive fillers
            
            # Overall fluency score
            fluency_score = (rate_score * 0.4 + pause_score * 0.3 + filler_score * 0.3)
            
            return {
                'score': float(fluency_score),
                'words_per_minute': float(wpm),
                'silence_ratio': float(silence_ratio),
                'filler_count': filler_count,
                'filler_ratio': float(filler_ratio),
                'rate_score': float(rate_score),
                'pause_score': float(pause_score),
                'filler_score': float(filler_score)
            }
            
        except Exception as e:
            logger.error(f"Fluency analysis failed: {e}")
            return {'score': 0.5, 'error': str(e)}
    
    def _analyze_pronunciation(self, audio_features: Dict, transcription_results: Dict) -> Dict:
        """Analyze pronunciation quality (basic metrics)"""
        try:
            # This is a simplified analysis - proper pronunciation analysis requires specialized models
            
            # Use transcription confidence as proxy for pronunciation clarity
            transcription_confidence = transcription_results.get('confidence', 0.5)
            
            # Analyze pitch variance (smoother speech often indicates better pronunciation)
            pitch_variance = audio_features.get('pitch_variance', 0)
            pitch_score = min(pitch_variance / 1000, 1.0) if pitch_variance > 0 else 0.5
            
            # Analyze spectral characteristics
            spectral_centroid = audio_features.get('avg_spectral_centroid', 1000)
            spectral_score = min(spectral_centroid / 2000, 1.0) if spectral_centroid > 0 else 0.5
            
            # Energy consistency (consistent volume often indicates clear speech)
            energy_variance = audio_features.get('energy_variance', 0)
            energy_score = max(0, 1 - energy_variance * 10)
            
            # Combined pronunciation score
            pronunciation_score = (
                transcription_confidence * 0.4 +
                pitch_score * 0.2 +
                spectral_score * 0.2 +
                energy_score * 0.2
            )
            
            return {
                'score': float(pronunciation_score),
                'transcription_confidence': float(transcription_confidence),
                'pitch_score': float(pitch_score),
                'spectral_score': float(spectral_score),
                'energy_score': float(energy_score),
                'note': 'Basic pronunciation analysis - detailed assessment requires specialized models'
            }
            
        except Exception as e:
            logger.error(f"Pronunciation analysis failed: {e}")
            return {'score': 0.5, 'error': str(e)}
    
    def _analyze_content(self, text: str, question_text: str = "") -> Dict:
        """Analyze content relevance and quality"""
        try:
            words = word_tokenize(text.lower())
            word_count = len([word for word in words if word.isalpha()])
            
            # Length appropriateness
            config = self.analysis_config
            if word_count >= config['optimal_response_length']:
                length_score = 1.0
            elif word_count >= config['min_response_length']:
                length_score = word_count / config['optimal_response_length']
            else:
                length_score = word_count / config['min_response_length'] * 0.5
            
            # Professional vocabulary usage
            professional_words = [
                word for word in words 
                if word in self.professional_vocabulary['positive_indicators']
            ]
            professional_ratio = len(professional_words) / word_count if word_count > 0 else 0
            professional_score = min(professional_ratio * 5, 1.0)  # Up to 20% professional words = full score
            
            # Sentence structure analysis
            sentences = sent_tokenize(text)
            avg_sentence_length = word_count / len(sentences) if sentences else 0
            structure_score = min(avg_sentence_length / 15, 1.0) if avg_sentence_length > 5 else 0.3
            
            # Relevance to question (basic keyword matching)
            relevance_score = 0.7  # Default neutral score
            if question_text:
                question_words = set(word_tokenize(question_text.lower()))
                response_words = set(words)
                common_words = question_words.intersection(response_words)
                if len(question_words) > 0:
                    relevance_score = min(len(common_words) / len(question_words) * 2, 1.0)
            
            # Overall content score
            content_score = (
                length_score * 0.3 +
                professional_score * 0.3 +
                structure_score * 0.2 +
                relevance_score * 0.2
            )
            
            return {
                'score': float(content_score),
                'word_count': word_count,
                'professional_words': len(professional_words),
                'professional_ratio': float(professional_ratio),
                'sentence_count': len(sentences),
                'avg_sentence_length': float(avg_sentence_length),
                'length_score': float(length_score),
                'professional_score': float(professional_score),
                'structure_score': float(structure_score),
                'relevance_score': float(relevance_score)
            }
            
        except Exception as e:
            logger.error(f"Content analysis failed: {e}")
            return {'score': 0.5, 'error': str(e)}
    
    def _analyze_formality(self, text: str) -> Dict:
        """Analyze formality and professionalism of language"""
        try:
            words = word_tokenize(text.lower())
            word_count = len([word for word in words if word.isalpha()])
            
            # Count informal words
            informal_words = [
                word for word in words 
                if word in self.professional_vocabulary['informal_words']
            ]
            informal_ratio = len(informal_words) / word_count if word_count > 0 else 0
            informal_penalty = min(informal_ratio * 3, 0.5)  # Max 50% penalty
            
            # Analyze sentence structure (basic)
            blob = TextBlob(text)
            sentences = blob.sentences
            
            # Check for complete sentences
            complete_sentences = sum(1 for sentence in sentences if len(sentence.words) > 3)
            completeness_score = complete_sentences / len(sentences) if sentences else 0
            
            # Check for contractions (less formal)
            contractions = ["n't", "'re", "'ve", "'ll", "'d", "'m", "'s"]
            contraction_count = sum(text.lower().count(contr) for contr in contractions)
            contraction_penalty = min(contraction_count / word_count * 2, 0.3) if word_count > 0 else 0
            
            # Calculate formality score
            formality_score = max(0, 1 - informal_penalty - contraction_penalty)
            formality_score = formality_score * completeness_score  # Apply completeness multiplier
            
            return {
                'score': float(formality_score),
                'informal_words': len(informal_words),
                'informal_ratio': float(informal_ratio),
                'contraction_count': contraction_count,
                'complete_sentences_ratio': float(completeness_score),
                'penalties': {
                    'informal_penalty': float(informal_penalty),
                    'contraction_penalty': float(contraction_penalty)
                }
            }
            
        except Exception as e:
            logger.error(f"Formality analysis failed: {e}")
            return {'score': 0.5, 'error': str(e)}
    
    def _analyze_confidence(self, text: str, audio_features: Dict) -> Dict:
        """Analyze confidence indicators in speech"""
        try:
            words = word_tokenize(text.lower())
            
            # Filler word analysis (fewer fillers = more confidence)
            filler_count = sum(1 for word in words if word in self.professional_vocabulary['filler_words'])
            filler_ratio = filler_count / len(words) if words else 0
            filler_confidence = max(0, 1 - (filler_ratio * 4))
            
            # Pace analysis (consistent pace = more confidence)
            speaking_rate = audio_features.get('speaking_rate', 0)
            optimal_rate = (self.analysis_config['min_words_per_minute'] + self.analysis_config['max_words_per_minute']) / 2
            rate_deviation = abs(speaking_rate - optimal_rate) / optimal_rate if optimal_rate > 0 else 1
            pace_confidence = max(0, 1 - rate_deviation)
            
            # Energy consistency (steady energy = more confidence)
            energy_variance = audio_features.get('energy_variance', 1)
            energy_confidence = max(0, 1 - energy_variance * 5)
            
            # Pause analysis (appropriate pauses = more confidence)
            silence_ratio = audio_features.get('silence_ratio', 0.5)
            optimal_silence = 0.2
            pause_deviation = abs(silence_ratio - optimal_silence) / optimal_silence
            pause_confidence = max(0, 1 - pause_deviation)
            
            # Overall confidence score
            confidence_score = (
                filler_confidence * 0.3 +
                pace_confidence * 0.25 +
                energy_confidence * 0.25 +
                pause_confidence * 0.2
            )
            
            return {
                'score': float(confidence_score),
                'filler_confidence': float(filler_confidence),
                'pace_confidence': float(pace_confidence),
                'energy_confidence': float(energy_confidence),
                'pause_confidence': float(pause_confidence),
                'metrics': {
                    'filler_ratio': float(filler_ratio),
                    'rate_deviation': float(rate_deviation),
                    'energy_variance': float(energy_variance),
                    'silence_ratio': float(silence_ratio)
                }
            }
            
        except Exception as e:
            logger.error(f"Confidence analysis failed: {e}")
            return {'score': 0.5, 'error': str(e)}
    
    def _calculate_analysis_confidence(self, details: Dict) -> float:
        """Calculate confidence in the analysis results"""
        confidence_factors = []
        
        # Transcription quality
        transcription_confidence = details.get('transcription', {}).get('confidence', 0.5)
        confidence_factors.append(transcription_confidence)
        
        # Audio quality indicators
        audio_features = details.get('audio_features', {})
        if 'error' not in audio_features:
            confidence_factors.append(0.8)
        
        # Word count (more words = more reliable analysis)
        word_count = details.get('transcription', {}).get('word_count', 0)
        word_confidence = min(word_count / 30, 1.0)  # 30 words for full confidence
        confidence_factors.append(word_confidence)
        
        return sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.3
    
    def _generate_feedback(self, results: Dict):
        """Generate specific feedback and recommendations"""
        feedback = []
        recommendations = []
        
        # Overall feedback
        overall_score = results.get('overall_score', 0)
        if overall_score >= 0.8:
            feedback.append("Excellent speech delivery and communication skills!")
        elif overall_score >= 0.6:
            feedback.append("Good communication with some areas for improvement.")
        else:
            feedback.append("Your speech delivery could be improved for professional settings.")
        
        # Fluency feedback
        fluency_score = results.get('fluency_score', 0)
        wpm = results.get('speaking_rate', 0)
        if fluency_score < 0.6:
            if wpm > 180:
                recommendations.append("Try to speak a bit slower for better clarity.")
            elif wpm < 120:
                recommendations.append("Try to speak with more energy and pace.")
            recommendations.append("Practice reducing filler words (um, uh, like).")
        
        # Content feedback
        content_score = results.get('content_score', 0)
        word_count = results.get('word_count', 0)
        if content_score < 0.6:
            if word_count < 20:
                recommendations.append("Provide more detailed responses to questions.")
            recommendations.append("Use more professional vocabulary to strengthen your answers.")
        
        # Formality feedback
        formality_score = results.get('formality_score', 0)
        if formality_score < 0.6:
            recommendations.append("Use more formal language appropriate for professional settings.")
            recommendations.append("Avoid contractions and casual expressions.")
        
        # Confidence feedback
        confidence_score = results.get('confidence_score', 0)
        if confidence_score < 0.6:
            recommendations.append("Practice speaking with more confidence and steady pace.")
            recommendations.append("Take brief pauses to collect your thoughts instead of using filler words.")
        
        results['feedback'] = feedback
        results['recommendations'] = recommendations
    
    def _calculate_overall_score(self, results: Dict) -> float:
        """Calculate weighted overall speech score"""
        try:
            config = self.analysis_config
            
            weighted_score = (
                results.get('fluency_score', 0) * config['fluency_weight'] +
                results.get('pronunciation_score', 0) * config['pronunciation_weight'] +
                results.get('content_score', 0) * config['content_weight'] +
                results.get('formality_score', 0) * config['formality_weight'] +
                results.get('confidence_score', 0) * config['confidence_weight']
            )
            
            # Apply analysis confidence weighting
            analysis_confidence = results.get('analysis_confidence', 0.5)
            confidence_adjusted_score = weighted_score * (0.3 + analysis_confidence * 0.7)
            
            return min(confidence_adjusted_score, 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating overall score: {e}")
            return 0.5
    
    def _error_result(self, error_message: str) -> Dict:
        """Return standardized error result"""
        return {
            'overall_score': 0.0,
            'error': error_message,
            'transcription': '',
            'word_count': 0,
            'feedback': ['Speech analysis failed due to technical error'],
            'recommendations': ['Please ensure clear audio recording and try again'],
            'analysis_confidence': 0.0,
            'timestamp': datetime.now().isoformat()
        }


# Singleton instance for web use
speech_analyzer = WebSpeechAnalyzer()

def analyze_speech(audio_data, question_text="", response_duration=None):
    """Main function for Django views to call"""
    return speech_analyzer.analyze_audio(audio_data, question_text, response_duration)

def quick_transcribe(audio_data):
    """Quick transcription function"""
    if not speech_analyzer.is_initialized:
        speech_analyzer.initialize_models()
    
    with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_file:
        temp_file.write(audio_data)
        temp_audio_path = temp_file.name
    
    try:
        result = speech_analyzer._transcribe_audio(temp_audio_path)
        return result.get('text', '')
    finally:
        if os.path.exists(temp_audio_path):
            os.unlink(temp_audio_path)