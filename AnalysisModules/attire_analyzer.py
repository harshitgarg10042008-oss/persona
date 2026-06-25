"""
Web-optimized attire analysis module for Django backend
Analyzes professional attire using CLIP, BLIP, and ViT models
"""

import torch
import cv2
import numpy as np
from PIL import Image, ImageDraw
import logging
from typing import Dict, List, Tuple, Optional
import json
import io
import base64

# ML imports
from transformers import CLIPProcessor, CLIPModel, BlipProcessor, BlipForConditionalGeneration
from transformers import ViTImageProcessor, ViTForImageClassification
import torchvision.transforms as transforms

logger = logging.getLogger(__name__)

class WebAttireAnalyzer:
    """Web-optimized attire analyzer for Django assessment system"""
    
    def __init__(self):
        self.clip_model = None
        self.clip_processor = None
        self.blip_model = None
        self.blip_processor = None
        self.vit_processor = None
        self.vit_model = None
        self.is_initialized = False
        
        # Professional attire knowledge base
        self.professional_standards = {
            'formal_business': {
                'colors': ['navy', 'black', 'charcoal', 'grey', 'white'],
                'patterns': ['solid', 'subtle stripes', 'small checks'],
                'attire_items': ['suit', 'blazer', 'dress shirt', 'tie', 'dress', 'blouse'],
                'shoes': ['oxford', 'loafer', 'pump', 'dress shoe'],
                'accessories': ['watch', 'simple jewelry', 'belt'],
                'score_weight': 1.0
            },
            'business_casual': {
                'colors': ['navy', 'black', 'grey', 'white', 'light blue', 'burgundy'],
                'patterns': ['solid', 'stripes', 'checks', 'subtle patterns'],
                'attire_items': ['blazer', 'cardigan', 'dress shirt', 'polo', 'blouse', 'sweater'],
                'shoes': ['loafer', 'oxford', 'flat', 'low heel'],
                'accessories': ['watch', 'jewelry', 'belt', 'scarf'],
                'score_weight': 0.8
            },
            'smart_casual': {
                'colors': ['various professional colors'],
                'patterns': ['most patterns acceptable'],
                'attire_items': ['shirt', 'blouse', 'sweater', 'nice top'],
                'shoes': ['clean sneakers', 'casual shoes', 'flats'],
                'accessories': ['minimal jewelry', 'watch'],
                'score_weight': 0.6
            }
        }
        
        # Analysis prompts for CLIP
        self.clip_prompts = [
            "a professionally dressed person in business attire",
            "someone wearing a formal suit",
            "a person in business casual clothing",
            "well-groomed professional appearance",
            "appropriate interview attire",
            "casual clothing",
            "inappropriate work attire",
            "unprofessional appearance"
        ]
    
    def initialize_models(self):
        """Initialize ML models - call once when needed"""
        try:
            if self.is_initialized:
                return True
                
            logger.info("Initializing attire analysis models...")
            
            # Initialize CLIP
            self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
            self.clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
            
            # Initialize BLIP
            self.blip_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
            self.blip_processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
            
            # Initialize ViT
            self.vit_processor = ViTImageProcessor.from_pretrained('google/vit-base-patch16-224')
            self.vit_model = ViTForImageClassification.from_pretrained('google/vit-base-patch16-224')
            
            self.is_initialized = True
            logger.info("Attire analysis models initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize attire analysis models: {e}")
            return False
    
    def analyze_image(self, image_data: bytes, assessment_type: str = 'formal_business') -> Dict:
        """
        Main analysis function for web use
        
        Args:
            image_data: Raw image bytes from webcam/upload
            assessment_type: Type of assessment ('formal_business', 'business_casual', 'smart_casual')
            
        Returns:
            Dict with analysis results and scores
        """
        try:
            if not self.is_initialized:
                if not self.initialize_models():
                    return self._error_result("Failed to initialize models")
            
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_data))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Run comprehensive analysis
            results = {
                'overall_score': 0.0,
                'professionalism_score': 0.0,
                'appropriateness_score': 0.0,
                'grooming_score': 0.0,
                'color_coordination_score': 0.0,
                'fit_score': 0.0,
                'details': {},
                'feedback': [],
                'recommendations': [],
                'assessment_type': assessment_type,
                'timestamp': None
            }
            
            # CLIP-based professionalism analysis
            clip_results = self._analyze_with_clip(image)
            results['professionalism_score'] = clip_results['score']
            results['details']['clip_analysis'] = clip_results
            
            # BLIP-based description and context
            blip_results = self._analyze_with_blip(image)
            results['details']['description'] = blip_results['description']
            results['details']['blip_analysis'] = blip_results
            
            # ViT-based classification
            vit_results = self._analyze_with_vit(image)
            results['details']['vit_analysis'] = vit_results
            
            # Color and coordination analysis
            color_results = self._analyze_colors(image)
            results['color_coordination_score'] = color_results['score']
            results['details']['color_analysis'] = color_results
            
            # Generate comprehensive feedback
            self._generate_feedback(results, assessment_type)
            
            # Calculate overall score
            results['overall_score'] = self._calculate_overall_score(results, assessment_type)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in attire analysis: {e}")
            return self._error_result(str(e))
    
    def _analyze_with_clip(self, image: Image.Image) -> Dict:
        """Analyze professionalism using CLIP model"""
        try:
            inputs = self.clip_processor(
                text=self.clip_prompts, 
                images=image, 
                return_tensors="pt", 
                padding=True
            )
            
            with torch.no_grad():
                outputs = self.clip_model(**inputs)
                logits_per_image = outputs.logits_per_image
                probs = logits_per_image.softmax(dim=1)
            
            # Calculate professionalism score
            professional_scores = probs[0][:5].sum().item()  # First 5 prompts are professional
            unprofessional_scores = probs[0][5:].sum().item()  # Last 3 are unprofessional
            
            score = professional_scores / (professional_scores + unprofessional_scores)
            
            return {
                'score': float(score),
                'professional_confidence': float(professional_scores),
                'unprofessional_confidence': float(unprofessional_scores),
                'detailed_scores': {
                    prompt: float(prob) for prompt, prob in zip(self.clip_prompts, probs[0])
                }
            }
            
        except Exception as e:
            logger.error(f"CLIP analysis failed: {e}")
            return {'score': 0.5, 'error': str(e)}
    
    def _analyze_with_blip(self, image: Image.Image) -> Dict:
        """Generate description using BLIP model"""
        try:
            inputs = self.blip_processor(image, return_tensors="pt")
            
            with torch.no_grad():
                out = self.blip_model.generate(**inputs, max_length=50)
                description = self.blip_processor.decode(out[0], skip_special_tokens=True)
            
            # Analyze description for professional keywords
            professional_keywords = [
                'suit', 'formal', 'business', 'professional', 'shirt', 'tie', 
                'blazer', 'dress', 'neat', 'clean', 'well-dressed'
            ]
            
            casual_keywords = [
                'casual', 't-shirt', 'jeans', 'sneakers', 'hoodie', 'shorts'
            ]
            
            prof_count = sum(1 for keyword in professional_keywords if keyword in description.lower())
            casual_count = sum(1 for keyword in casual_keywords if keyword in description.lower())
            
            return {
                'description': description,
                'professional_keywords': prof_count,
                'casual_keywords': casual_count,
                'description_score': min(prof_count / max(len(professional_keywords) * 0.3, 1), 1.0)
            }
            
        except Exception as e:
            logger.error(f"BLIP analysis failed: {e}")
            return {'description': 'Analysis failed', 'error': str(e)}
    
    def _analyze_with_vit(self, image: Image.Image) -> Dict:
        """Classification using ViT model"""
        try:
            inputs = self.vit_processor(images=image, return_tensors="pt")
            
            with torch.no_grad():
                outputs = self.vit_model(**inputs)
                predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
            
            # Get top predictions
            top_predictions = torch.topk(predictions, 5)
            
            results = {
                'top_classes': [],
                'confidence_scores': []
            }
            
            for score, idx in zip(top_predictions.values[0], top_predictions.indices[0]):
                class_name = self.vit_model.config.id2label[idx.item()]
                results['top_classes'].append(class_name)
                results['confidence_scores'].append(float(score))
            
            return results
            
        except Exception as e:
            logger.error(f"ViT analysis failed: {e}")
            return {'error': str(e)}
    
    def _analyze_colors(self, image: Image.Image) -> Dict:
        """Analyze color coordination and professionalism"""
        try:
            # Convert to numpy array for color analysis
            img_array = np.array(image)
            
            # Get dominant colors
            pixels = img_array.reshape(-1, 3)
            
            # Simple color analysis - check for professional color palette
            professional_colors = {
                'navy': [30, 50, 80],
                'black': [20, 20, 20],
                'white': [240, 240, 240],
                'grey': [128, 128, 128],
                'brown': [139, 69, 19]
            }
            
            # Calculate color distribution
            color_scores = {}
            for color_name, target_rgb in professional_colors.items():
                # Calculate how much of the image matches this professional color
                distances = np.sqrt(np.sum((pixels - target_rgb) ** 2, axis=1))
                close_matches = np.sum(distances < 50)  # Threshold for color similarity
                color_scores[color_name] = close_matches / len(pixels)
            
            # Overall professional color score
            prof_color_ratio = sum(color_scores.values())
            
            return {
                'score': min(prof_color_ratio * 2, 1.0),  # Scale to 0-1
                'color_distribution': color_scores,
                'dominant_professional_colors': [
                    color for color, ratio in color_scores.items() if ratio > 0.1
                ]
            }
            
        except Exception as e:
            logger.error(f"Color analysis failed: {e}")
            return {'score': 0.5, 'error': str(e)}
    
    def _generate_feedback(self, results: Dict, assessment_type: str):
        """Generate specific feedback and recommendations"""
        feedback = []
        recommendations = []
        
        overall_score = results.get('overall_score', 0)
        
        if overall_score >= 0.8:
            feedback.append("Excellent professional appearance!")
            feedback.append("Your attire demonstrates strong attention to professional standards.")
        elif overall_score >= 0.6:
            feedback.append("Good professional appearance with room for improvement.")
            recommendations.append("Consider refining some aspects of your professional presentation.")
        else:
            feedback.append("Your attire could be more professional for this setting.")
            recommendations.append("Focus on wearing more formal business attire.")
        
        # Specific feedback based on analysis components
        if results.get('color_coordination_score', 0) < 0.5:
            recommendations.append("Consider wearing more traditional professional colors like navy, black, or grey.")
        
        if results.get('professionalism_score', 0) < 0.6:
            recommendations.append("Ensure your attire aligns with formal business standards.")
        
        # Assessment type specific feedback
        standards = self.professional_standards.get(assessment_type, {})
        if standards:
            recommendations.append(f"For {assessment_type.replace('_', ' ')} settings, focus on: {', '.join(standards.get('attire_items', [])[:3])}")
        
        results['feedback'] = feedback
        results['recommendations'] = recommendations
    
    def _calculate_overall_score(self, results: Dict, assessment_type: str) -> float:
        """Calculate weighted overall score"""
        try:
            weights = {
                'professionalism_score': 0.4,
                'color_coordination_score': 0.2,
                'appropriateness_score': 0.2,
                'grooming_score': 0.1,
                'fit_score': 0.1
            }
            
            # Get assessment type weight
            type_weight = self.professional_standards.get(assessment_type, {}).get('score_weight', 0.8)
            
            weighted_score = 0.0
            total_weight = 0.0
            
            for component, weight in weights.items():
                if component in results and results[component] is not None:
                    weighted_score += results[component] * weight
                    total_weight += weight
            
            if total_weight > 0:
                base_score = weighted_score / total_weight
                return min(base_score * type_weight, 1.0)
            
            return 0.5  # Default score if no components available
            
        except Exception as e:
            logger.error(f"Error calculating overall score: {e}")
            return 0.5
    
    def _error_result(self, error_message: str) -> Dict:
        """Return standardized error result"""
        return {
            'overall_score': 0.0,
            'error': error_message,
            'feedback': ['Analysis failed due to technical error'],
            'recommendations': ['Please try again or contact support'],
            'timestamp': None
        }
    
    def analyze_base64_image(self, base64_data: str, assessment_type: str = 'formal_business') -> Dict:
        """Convenience method for base64 image data from web frontend"""
        try:
            # Remove data URL prefix if present
            if ',' in base64_data:
                base64_data = base64_data.split(',')[1]
            
            # Decode base64 to bytes
            image_bytes = base64.b64decode(base64_data)
            
            return self.analyze_image(image_bytes, assessment_type)
            
        except Exception as e:
            logger.error(f"Error processing base64 image: {e}")
            return self._error_result(f"Invalid image data: {e}")


# Singleton instance for web use
attire_analyzer = WebAttireAnalyzer()

def analyze_attire(image_data, assessment_type='formal_business'):
    """Main function for Django views to call"""
    return attire_analyzer.analyze_image(image_data, assessment_type)

def analyze_attire_base64(base64_data, assessment_type='formal_business'):
    """Function for analyzing base64 images from web frontend"""
    return attire_analyzer.analyze_base64_image(base64_data, assessment_type)