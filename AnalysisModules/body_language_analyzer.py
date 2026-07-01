"""
Web-optimized body language analysis module for Django backend
Analyzes posture, eye contact, and gestures using MediaPipe
"""

import cv2
import numpy as np
import mediapipe as mp
import logging
from typing import Dict, List, Tuple, Optional
import json
import io
import base64
from PIL import Image
import math

logger = logging.getLogger(__name__)

class WebBodyLanguageAnalyzer:
    """Web-optimized body language analyzer for Django assessment system"""
    
    def __init__(self):
        try:
            self.mp_pose = mp.solutions.pose
            self.mp_face_mesh = mp.solutions.face_mesh
            self.mp_hands = mp.solutions.hands
            self.mp_drawing = mp.solutions.drawing_utils
            self.mediapipe_available = True
        except Exception as e:
            logger.warning(
                f"MediaPipe initialization failed — body language analysis will be disabled. "
                f"Reason: {e}"
            )
            self.mp_pose = None
            self.mp_face_mesh = None
            self.mp_hands = None
            self.mp_drawing = None
            self.mediapipe_available = False
            self.is_initialized = False
            return

        # Initialize MediaPipe detector handles (created lazily in initialize_detectors)
        self.pose_detector = None
        self.face_mesh_detector = None
        self.hands_detector = None
        self.is_initialized = False
        
        # Analysis thresholds and weights
        self.analysis_config = {
            'posture_weight': 0.35,
            'eye_contact_weight': 0.25,
            'gesture_weight': 0.20,
            'face_orientation_weight': 0.20,
            
            # Posture thresholds
            'good_posture_threshold': 0.7,
            'shoulder_alignment_threshold': 0.1,
            'spine_straightness_threshold': 0.15,
            
            # Eye contact thresholds
            'direct_gaze_threshold': 0.3,
            'gaze_deviation_threshold': 0.5,
            
            # Gesture thresholds
            'excessive_movement_threshold': 0.8,
            'minimal_movement_threshold': 0.2,
        }
    
    def initialize_detectors(self):
        """Initialize MediaPipe detectors - call once when needed"""
        try:
            if not getattr(self, 'mediapipe_available', True):
                logger.warning("Cannot initialize detectors: mediapipe not available")
                return False
                
            if self.is_initialized:
                return True
                
            logger.info("Initializing body language analysis detectors...")
            
            # Initialize pose detection
            self.pose_detector = self.mp_pose.Pose(
                static_image_mode=True,
                model_complexity=1,
                smooth_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
            
            # Initialize face mesh
            self.face_mesh_detector = self.mp_face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
            
            # Initialize hand detection
            self.hands_detector = self.mp_hands.Hands(
                static_image_mode=True,
                max_num_hands=2,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
            
            self.is_initialized = True
            logger.info("Body language analysis detectors initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize body language detectors: {e}")
            return False
    
    def analyze_image(self, image_data: bytes) -> Dict:
        """
        Main analysis function for web use
        
        Args:
            image_data: Raw image bytes from webcam
            
        Returns:
            Dict with analysis results and scores
        """
        try:
            if not self.is_initialized:
                if not self.initialize_detectors():
                    return self._error_result("Failed to initialize detectors")
            
            # Convert bytes to OpenCV image
            nparr = np.frombuffer(image_data, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is None:
                return self._error_result("Invalid image data")
            
            # Convert BGR to RGB for MediaPipe
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # Initialize results structure
            results = {
                'overall_score': 0.0,
                'posture_score': 0.0,
                'eye_contact_score': 0.0,
                'gesture_score': 0.0,
                'face_orientation_score': 0.0,
                'details': {},
                'feedback': [],
                'recommendations': [],
                'confidence': 0.0,
                'timestamp': None
            }
            
            # Analyze posture
            posture_results = self._analyze_posture(rgb_image)
            results['posture_score'] = posture_results['score']
            results['details']['posture'] = posture_results
            
            # Analyze eye contact and face orientation
            face_results = self._analyze_face_orientation(rgb_image)
            results['eye_contact_score'] = face_results['eye_contact_score']
            results['face_orientation_score'] = face_results['orientation_score']
            results['details']['face'] = face_results
            
            # Analyze hand gestures
            gesture_results = self._analyze_gestures(rgb_image)
            results['gesture_score'] = gesture_results['score']
            results['details']['gestures'] = gesture_results
            
            # Calculate overall confidence
            results['confidence'] = self._calculate_confidence(results['details'])
            
            # Generate feedback and recommendations
            self._generate_feedback(results)
            
            # Calculate overall score
            results['overall_score'] = self._calculate_overall_score(results)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in body language analysis: {e}")
            return self._error_result(str(e))
    
    def _analyze_posture(self, image: np.ndarray) -> Dict:
        """Analyze posture using pose detection"""
        try:
            pose_results = self.pose_detector.process(image)
            
            if not pose_results.pose_landmarks:
                return {
                    'score': 0.5,
                    'detected': False,
                    'error': 'No pose detected'
                }
            
            landmarks = pose_results.pose_landmarks.landmark
            
            # Extract key points
            left_shoulder = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER]
            right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER]
            left_hip = landmarks[self.mp_pose.PoseLandmark.LEFT_HIP]
            right_hip = landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP]
            nose = landmarks[self.mp_pose.PoseLandmark.NOSE]
            
            # Calculate shoulder alignment
            shoulder_diff = abs(left_shoulder.y - right_shoulder.y)
            shoulder_alignment_score = max(0, 1 - (shoulder_diff / self.analysis_config['shoulder_alignment_threshold']))
            
            # Calculate spine straightness (nose to midpoint of hips)
            hip_midpoint_x = (left_hip.x + right_hip.x) / 2
            hip_midpoint_y = (left_hip.y + right_hip.y) / 2
            spine_deviation = abs(nose.x - hip_midpoint_x)
            spine_straightness_score = max(0, 1 - (spine_deviation / self.analysis_config['spine_straightness_threshold']))
            
            # Calculate head position relative to shoulders
            shoulder_midpoint_y = (left_shoulder.y + right_shoulder.y) / 2
            head_forward_lean = max(0, shoulder_midpoint_y - nose.y)
            head_position_score = max(0, 1 - (head_forward_lean * 2))
            
            # Overall posture score
            posture_score = (
                shoulder_alignment_score * 0.4 +
                spine_straightness_score * 0.4 +
                head_position_score * 0.2
            )
            
            return {
                'score': float(posture_score),
                'detected': True,
                'shoulder_alignment': float(shoulder_alignment_score),
                'spine_straightness': float(spine_straightness_score),
                'head_position': float(head_position_score),
                'metrics': {
                    'shoulder_difference': float(shoulder_diff),
                    'spine_deviation': float(spine_deviation),
                    'head_forward_lean': float(head_forward_lean)
                }
            }
            
        except Exception as e:
            logger.error(f"Posture analysis failed: {e}")
            return {'score': 0.5, 'detected': False, 'error': str(e)}
    
    def _analyze_face_orientation(self, image: np.ndarray) -> Dict:
        """Analyze face orientation and estimate eye contact"""
        try:
            face_results = self.face_mesh_detector.process(image)
            
            if not face_results.multi_face_landmarks:
                return {
                    'eye_contact_score': 0.5,
                    'orientation_score': 0.5,
                    'detected': False,
                    'error': 'No face detected'
                }
            
            face_landmarks = face_results.multi_face_landmarks[0]
            landmarks = face_landmarks.landmark
            
            # Key facial landmarks for orientation analysis
            nose_tip = landmarks[1]
            left_eye_outer = landmarks[33]
            right_eye_outer = landmarks[263]
            left_mouth = landmarks[61]
            right_mouth = landmarks[291]
            
            # Calculate face orientation based on eye and mouth symmetry
            eye_center_x = (left_eye_outer.x + right_eye_outer.x) / 2
            mouth_center_x = (left_mouth.x + right_mouth.x) / 2
            face_center_x = (eye_center_x + mouth_center_x) / 2
            
            # Estimate face orientation (0.5 = forward facing)
            face_orientation_deviation = abs(face_center_x - 0.5)
            orientation_score = max(0, 1 - (face_orientation_deviation * 2))
            
            # Estimate eye contact based on face orientation
            # More sophisticated eye tracking would require additional models
            eye_contact_score = orientation_score * 0.8  # Conservative estimate
            
            # Analyze eye region for additional cues
            left_eye_landmarks = [landmarks[i] for i in [33, 7, 163, 144, 145, 153, 154, 155, 133]]
            right_eye_landmarks = [landmarks[i] for i in [362, 382, 381, 380, 374, 373, 390, 249, 263]]
            
            # Calculate eye openness (simple metric)
            left_eye_height = abs(landmarks[145].y - landmarks[159].y)
            right_eye_height = abs(landmarks[374].y - landmarks[386].y)
            avg_eye_height = (left_eye_height + right_eye_height) / 2
            
            # Normalize eye openness (this is a rough approximation)
            eye_openness_score = min(avg_eye_height * 50, 1.0)  # Scale factor may need adjustment
            
            return {
                'eye_contact_score': float(eye_contact_score),
                'orientation_score': float(orientation_score),
                'eye_openness_score': float(eye_openness_score),
                'detected': True,
                'metrics': {
                    'face_orientation_deviation': float(face_orientation_deviation),
                    'face_center_x': float(face_center_x),
                    'avg_eye_height': float(avg_eye_height)
                }
            }
            
        except Exception as e:
            logger.error(f"Face orientation analysis failed: {e}")
            return {
                'eye_contact_score': 0.5,
                'orientation_score': 0.5,
                'detected': False,
                'error': str(e)
            }
    
    def _analyze_gestures(self, image: np.ndarray) -> Dict:
        """Analyze hand gestures and movement"""
        try:
            hand_results = self.hands_detector.process(image)
            
            if not hand_results.multi_hand_landmarks:
                return {
                    'score': 0.6,  # Neutral score for no visible hands
                    'detected': False,
                    'hands_count': 0,
                    'message': 'No hands visible in frame'
                }
            
            hands_data = []
            total_movement_score = 0
            
            for hand_landmarks, handedness in zip(hand_results.multi_hand_landmarks, hand_results.multi_handedness):
                hand_label = handedness.classification[0].label
                landmarks = hand_landmarks.landmark
                
                # Calculate hand position relative to body
                hand_center_x = sum(lm.x for lm in landmarks) / len(landmarks)
                hand_center_y = sum(lm.y for lm in landmarks) / len(landmarks)
                
                # Analyze gesture appropriateness (hands in professional zone)
                # Professional zone: roughly torso level, not too high or low
                appropriate_y_range = (0.3, 0.8)  # Relative to image height
                appropriate_x_range = (0.2, 0.8)  # Relative to image width
                
                position_appropriateness = 1.0
                if hand_center_y < appropriate_y_range[0] or hand_center_y > appropriate_y_range[1]:
                    position_appropriateness *= 0.7
                if hand_center_x < appropriate_x_range[0] or hand_center_x > appropriate_x_range[1]:
                    position_appropriateness *= 0.8
                
                # Analyze finger positions for excessive gesturing
                # Calculate spread of landmarks to detect excessive movement
                x_coords = [lm.x for lm in landmarks]
                y_coords = [lm.y for lm in landmarks]
                hand_spread = (max(x_coords) - min(x_coords)) + (max(y_coords) - min(y_coords))
                
                # Score based on hand spread (too much indicates excessive gesturing)
                spread_score = max(0, 1 - (hand_spread - 0.1) * 2) if hand_spread > 0.1 else 1.0
                
                hand_score = (position_appropriateness * 0.6 + spread_score * 0.4)
                total_movement_score += hand_score
                
                hands_data.append({
                    'hand': hand_label,
                    'position': {'x': float(hand_center_x), 'y': float(hand_center_y)},
                    'spread': float(hand_spread),
                    'position_score': float(position_appropriateness),
                    'spread_score': float(spread_score),
                    'overall_score': float(hand_score)
                })
            
            # Average score across all detected hands
            gesture_score = total_movement_score / len(hands_data) if hands_data else 0.6
            
            return {
                'score': float(gesture_score),
                'detected': True,
                'hands_count': len(hands_data),
                'hands_data': hands_data,
                'message': f"Detected {len(hands_data)} hand(s)"
            }
            
        except Exception as e:
            logger.error(f"Gesture analysis failed: {e}")
            return {'score': 0.5, 'detected': False, 'error': str(e)}
    
    def _calculate_confidence(self, details: Dict) -> float:
        """Calculate overall confidence based on detection success"""
        confidence_factors = []
        
        if details.get('posture', {}).get('detected'):
            confidence_factors.append(0.9)
        if details.get('face', {}).get('detected'):
            confidence_factors.append(0.9)
        if details.get('gestures', {}).get('detected'):
            confidence_factors.append(0.8)
        
        return sum(confidence_factors) / 3 if confidence_factors else 0.3
    
    def _generate_feedback(self, results: Dict):
        """Generate specific feedback and recommendations"""
        feedback = []
        recommendations = []
        
        # Posture feedback
        posture_score = results.get('posture_score', 0)
        if posture_score >= 0.8:
            feedback.append("Excellent posture! You appear confident and professional.")
        elif posture_score >= 0.6:
            feedback.append("Good posture with minor areas for improvement.")
            recommendations.append("Focus on keeping your shoulders level and spine straight.")
        else:
            feedback.append("Your posture could be improved for a more professional appearance.")
            recommendations.append("Sit up straight with shoulders back and aligned.")
        
        # Eye contact feedback
        eye_contact_score = results.get('eye_contact_score', 0)
        if eye_contact_score >= 0.7:
            feedback.append("Good eye contact and face orientation.")
        elif eye_contact_score >= 0.5:
            recommendations.append("Try to look more directly at the camera.")
        else:
            recommendations.append("Maintain better eye contact by looking directly at the camera.")
        
        # Gesture feedback
        gesture_score = results.get('gesture_score', 0)
        if gesture_score >= 0.7:
            feedback.append("Appropriate hand positioning and gestures.")
        else:
            recommendations.append("Keep hand movements natural and within the professional zone.")
        
        # Overall feedback
        overall_score = results.get('overall_score', 0)
        if overall_score >= 0.8:
            feedback.append("Overall excellent body language for a professional setting!")
        elif overall_score >= 0.6:
            feedback.append("Good body language with room for minor improvements.")
        else:
            feedback.append("Focus on improving your overall body language and presence.")
        
        results['feedback'] = feedback
        results['recommendations'] = recommendations
    
    def _calculate_overall_score(self, results: Dict) -> float:
        """Calculate weighted overall body language score"""
        try:
            config = self.analysis_config
            
            weighted_score = (
                results.get('posture_score', 0) * config['posture_weight'] +
                results.get('eye_contact_score', 0) * config['eye_contact_weight'] +
                results.get('gesture_score', 0) * config['gesture_weight'] +
                results.get('face_orientation_score', 0) * config['face_orientation_weight']
            )
            
            # Apply confidence weighting
            confidence = results.get('confidence', 0.5)
            confidence_adjusted_score = weighted_score * (0.5 + confidence * 0.5)
            
            return min(confidence_adjusted_score, 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating overall score: {e}")
            return 0.5
    
    def _error_result(self, error_message: str) -> Dict:
        """Return standardized error result"""
        return {
            'overall_score': 0.0,
            'error': error_message,
            'feedback': ['Analysis failed due to technical error'],
            'recommendations': ['Please ensure good lighting and camera positioning'],
            'confidence': 0.0,
            'timestamp': None
        }
    
    def analyze_base64_image(self, base64_data: str) -> Dict:
        """Convenience method for base64 image data from web frontend"""
        try:
            # Remove data URL prefix if present
            if ',' in base64_data:
                base64_data = base64_data.split(',')[1]
            
            # Decode base64 to bytes
            image_bytes = base64.b64decode(base64_data)
            
            return self.analyze_image(image_bytes)
            
        except Exception as e:
            logger.error(f"Error processing base64 image: {e}")
            return self._error_result(f"Invalid image data: {e}")


# Singleton instance for web use
body_language_analyzer = WebBodyLanguageAnalyzer()

def analyze_body_language(image_data):
    """Main function for Django views to call"""
    return body_language_analyzer.analyze_image(image_data)

def analyze_body_language_base64(base64_data):
    """Function for analyzing base64 images from web frontend"""
    return body_language_analyzer.analyze_base64_image(base64_data)