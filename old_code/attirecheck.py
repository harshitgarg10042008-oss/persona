import cv2
import numpy as np
import torch
import torchvision.transforms as transforms
from PIL import Image, ImageDraw, ImageFont
import clip
import requests
import io
import base64
import json
import os
from pathlib import Path
import argparse
from transformers import (
    BlipProcessor, BlipForConditionalGeneration,
    ViTImageProcessor, ViTForImageClassification,
    pipeline
)
import mediapipe as mp
import warnings
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics.pairwise import cosine_similarity
from collections import defaultdict
import time

warnings.filterwarnings('ignore')

class AdvancedAttireAnalyzer:
    def __init__(self):
        print("🚀 Initializing Advanced Attire Analysis System...")
        
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"💻 Using device: {self.device}")
        
        self.models = {}
        self.load_all_models()
        
        # this is where we store all the professional stuff
        self.professional_standards = self.build_professional_knowledge_base()
        
        print("✅ Advanced Attire Analyzer Ready!")
    
    def load_all_models(self):
        
        # 1. clip - vision language thing
        try:
            print("📥 Loading CLIP (Vision-Language Model)...")
            self.models['clip_model'], self.models['clip_preprocess'] = clip.load("ViT-L/14", device=self.device)
            print("✅ CLIP Model Loaded")
        except Exception as e:
            print(f"❌ CLIP Failed: {e}")
            self.models['clip_model'] = None
        
        # 2. blip for captions
        try:
            print("📥 Loading BLIP (Image Captioning)...")
            self.models['blip_processor'] = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-large")
            self.models['blip_model'] = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-large")
            print("✅ BLIP Model Loaded")
        except Exception as e:
            print(f"❌ BLIP Failed: {e}")
            self.models['blip_processor'] = None
        
        # 3. fashion vit thing
        try:
            print("📥 Loading Fashion ViT Model...")
            self.models['fashion_processor'] = ViTImageProcessor.from_pretrained('google/vit-base-patch16-224')
            self.models['fashion_model'] = ViTForImageClassification.from_pretrained('google/vit-base-patch16-224')
            print("✅ Fashion ViT Model Loaded")
        except Exception as e:
            print(f"❌ Fashion ViT Failed: {e}")
            self.models['fashion_processor'] = None
        
        # 4. some pipeline that probably doesn't work
        try:
            print("📥 Loading Multi-modal Pipeline...")
            self.models['classifier'] = pipeline(
                "image-classification",
                model="microsoft/DiT-base-distilled-patch16-224",
                device=0 if torch.cuda.is_available() else -1
            )
            print("✅ Multi-modal Pipeline Loaded")
        except Exception as e:
            print(f"❌ Multi-modal Pipeline Failed: {e}")
            self.models['classifier'] = None
        
        # 5. mediapipe for finding people
        try:
            print("📥 Loading MediaPipe...")
            self.mp_selfie = mp.solutions.selfie_segmentation
            self.mp_pose = mp.solutions.pose
            self.selfie_segmentation = self.mp_selfie.SelfieSegmentation(model_selection=1)
            self.pose_detection = self.mp_pose.Pose(
                static_image_mode=True,
                min_detection_confidence=0.8
            )
            print("✅ MediaPipe Loaded")
        except Exception as e:
            print(f"❌ MediaPipe Failed: {e}")
    
    def build_professional_knowledge_base(self):
        # basically what counts as professional vs not
        return {
            'formal_business': {
                'score_range': (85, 100),
                'keywords': [
                    'business suit', 'formal suit', 'three-piece suit', 'two-piece suit',
                    'blazer', 'suit jacket', 'dress shirt', 'button-down shirt',
                    'necktie', 'bow tie', 'formal tie', 'silk tie',
                    'dress pants', 'suit pants', 'formal trousers',
                    'formal dress', 'business dress', 'cocktail dress',
                    'oxford shoes', 'dress shoes', 'formal shoes', 'leather shoes',
                    'formal blouse', 'professional blouse'
                ],
                'colors': ['black', 'navy', 'charcoal', 'gray', 'white', 'cream'],
                'patterns': ['solid', 'pinstripe', 'subtle pattern', 'conservative'],
                'description': 'Highly Professional - Perfect for formal business meetings'
            },
            'business_casual': {
                'score_range': (65, 84),
                'keywords': [
                    'blazer', 'sport coat', 'casual blazer',
                    'dress shirt', 'polo shirt', 'professional polo',
                    'chinos', 'khakis', 'dress pants',
                    'sweater', 'cardigan', 'pullover',
                    'blouse', 'professional top',
                    'loafers', 'dress casual shoes',
                    'skirt', 'professional skirt'
                ],
                'colors': ['navy', 'khaki', 'brown', 'burgundy', 'forest green'],
                'patterns': ['solid', 'subtle check', 'small pattern'],
                'description': 'Professional - Suitable for most business environments'
            },
            'smart_casual': {
                'score_range': (45, 64),
                'keywords': [
                    'casual shirt', 'button-up shirt',
                    'sweater', 'cardigan',
                    'dark jeans', 'neat jeans',
                    'casual dress', 'sundress',
                    'casual shoes', 'clean sneakers'
                ],
                'colors': ['various'],
                'patterns': ['casual patterns', 'stripes', 'checks'],
                'description': 'Casual Professional - OK for casual Fridays'
            },
            'too_casual': {
                'score_range': (20, 44),
                'keywords': [
                    't-shirt', 'graphic tee', 'casual t-shirt',
                    'jeans', 'ripped jeans', 'faded jeans',
                    'shorts', 'cargo shorts',
                    'sneakers', 'athletic shoes',
                    'hoodie', 'sweatshirt'
                ],
                'colors': ['bright colors', 'neon'],
                'patterns': ['graphic prints', 'logos'],
                'description': 'Too Casual - Not suitable for professional settings'
            },
            'inappropriate': {
                'score_range': (0, 19),
                'keywords': [
                    'tank top', 'sleeveless shirt', 'crop top',
                    'shorts', 'mini skirt', 'very short skirt',
                    'flip flops', 'sandals', 'beach wear',
                    'athletic wear', 'gym clothes', 'workout clothes',
                    'pajamas', 'sleepwear', 'loungewear',
                    'swimwear', 'bikini', 'swimming attire'
                ],
                'colors': ['any'],
                'patterns': ['any'],
                'description': 'Inappropriate - Not suitable for any professional environment'
            }
        }
    
    def preprocess_image(self, image_path):
        try:
            # load and convert image
            if isinstance(image_path, str):
                image = Image.open(image_path).convert('RGB')
            else:
                image = image_path.convert('RGB')
            
            image_np = np.array(image)
            
            # get person mask using mediapipe
            results = self.selfie_segmentation.process(image_np)
            mask = results.segmentation_mask
            
            # apply mask to focus on person only
            mask_3d = np.stack((mask,) * 3, axis=-1) > 0.1
            person_image = image_np * mask_3d
            
            person_pil = Image.fromarray(person_image.astype(np.uint8))
            
            # get pose stuff
            pose_results = self.pose_detection.process(image_np)
            
            # try to extract clothing regions if we have pose
            upper_body_region = None
            lower_body_region = None
            
            if pose_results.pose_landmarks:
                upper_body_region, lower_body_region = self.extract_clothing_regions(
                    person_pil, pose_results.pose_landmarks, image_np.shape
                )
            
            return {
                'original': image,
                'person_segmented': person_pil,
                'upper_body': upper_body_region,
                'lower_body': lower_body_region,
                'pose_landmarks': pose_results.pose_landmarks,
                'segmentation_mask': mask
            }
            
        except Exception as e:
            print(f"❌ Preprocessing error: {e}")
            return {'original': image, 'person_segmented': image}
    
    def extract_clothing_regions(self, image, pose_landmarks, image_shape):
        # try to get shirt and pants regions using pose landmarks
        try:
            h, w = image_shape[:2]
            image_np = np.array(image)
            
            # get important body points
            landmarks = pose_landmarks.landmark
            left_shoulder = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value]
            right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
            left_hip = landmarks[self.mp_pose.PoseLandmark.LEFT_HIP.value]
            right_hip = landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP.value]
            
            # convert to actual pixels
            left_shoulder_px = (int(left_shoulder.x * w), int(left_shoulder.y * h))
            right_shoulder_px = (int(right_shoulder.x * w), int(right_shoulder.y * h))
            left_hip_px = (int(left_hip.x * w), int(left_hip.y * h))
            right_hip_px = (int(right_hip.x * w), int(right_hip.y * h))
            
            margin = 50
            
            # upper body area (shirt/jacket region)
            upper_top = max(0, min(left_shoulder_px[1], right_shoulder_px[1]) - margin)
            upper_bottom = min(h, max(left_hip_px[1], right_hip_px[1]))
            upper_left = max(0, min(left_shoulder_px[0], right_shoulder_px[0]) - margin)
            upper_right = min(w, max(left_shoulder_px[0], right_shoulder_px[0]) + margin)
            
            # lower body area (pants/skirt)
            lower_top = max(0, max(left_hip_px[1], right_hip_px[1]) - 20)
            lower_bottom = h
            lower_left = max(0, min(left_hip_px[0], right_hip_px[0]) - margin)
            lower_right = min(w, max(left_hip_px[0], right_hip_px[0]) + margin)
            
            # cut out the regions
            upper_region = image_np[upper_top:upper_bottom, upper_left:upper_right]
            lower_region = image_np[lower_top:lower_bottom, lower_left:lower_right]
            
            upper_pil = Image.fromarray(upper_region) if upper_region.size > 0 else None
            lower_pil = Image.fromarray(lower_region) if lower_region.size > 0 else None
            
            return upper_pil, lower_pil
            
        except Exception as e:
            print(f"❌ Region extraction error: {e}")
            return None, None
    
    def analyze_with_clip(self, image_data):
        if self.models['clip_model'] is None:
            return None
        
        try:
            results = {}
            
            # check different parts of the image
            regions_to_analyze = {
                'full_person': image_data['person_segmented'],
                'upper_body': image_data.get('upper_body'),
                'lower_body': image_data.get('lower_body')
            }
            
            for region_name, region_image in regions_to_analyze.items():
                if region_image is None:
                    continue
                
                image_input = self.models['clip_preprocess'](region_image).unsqueeze(0).to(self.device)
                
                # different prompts for different regions
                if region_name == 'full_person':
                    prompts = [
                        "a person wearing a formal business suit with tie",
                        "a person wearing a professional blazer and dress shirt",
                        "a person wearing business casual attire",
                        "a person wearing smart casual clothes",
                        "a person wearing casual everyday clothes",
                        "a person wearing inappropriate work attire",
                        "a person in formal professional business attire",
                        "a person dressed for a corporate meeting",
                        "a person wearing expensive formal clothing",
                        "a person wearing high-quality professional attire"
                    ]
                elif region_name == 'upper_body':
                    prompts = [
                        "formal dress shirt with tie",
                        "business blazer or suit jacket", 
                        "professional blouse or shirt",
                        "casual shirt or top",
                        "t-shirt or casual wear",
                        "inappropriate or revealing top"
                    ]
                else:  # lower_body
                    prompts = [
                        "formal dress pants or suit trousers",
                        "business casual pants or chinos",
                        "professional skirt or dress pants",
                        "casual jeans or pants",
                        "shorts or inappropriate bottoms",
                        "athletic or gym wear"
                    ]
                
                # Tokenize prompts
                text_inputs = clip.tokenize(prompts).to(self.device)
                
                # Get predictions
                with torch.no_grad():
                    logits_per_image, logits_per_text = self.models['clip_model'](image_input, text_inputs)
                    probs = logits_per_image.softmax(dim=-1).cpu().numpy()[0]
                
                # Store results
                results[region_name] = {
                    'prompts': prompts,
                    'probabilities': probs,
                    'best_match': prompts[np.argmax(probs)],
                    'confidence': float(np.max(probs))
                }
            
            return results
            
        except Exception as e:
            print(f"❌ CLIP analysis error: {e}")
            return None
    
    def analyze_with_blip(self, image_data):
        if self.models['blip_processor'] is None:
            return None
        
        try:
            results = {}
            
            image = image_data['person_segmented']
            
            # get caption from blip
            inputs = self.models['blip_processor'](image, return_tensors="pt")
            
            with torch.no_grad():
                captions = []
                
                # standard caption
                out = self.models['blip_model'].generate(**inputs, max_length=100, num_beams=5)
                caption = self.models['blip_processor'].decode(out[0], skip_special_tokens=True)
                captions.append(caption)
                
                # detailed one
                out = self.models['blip_model'].generate(**inputs, max_length=150, num_beams=8, temperature=0.7)
                detailed_caption = self.models['blip_processor'].decode(out[0], skip_special_tokens=True)
                captions.append(detailed_caption)
            
            results = {
                'captions': captions,
                'primary_description': captions[0],
                'detailed_description': captions[1] if len(captions) > 1 else captions[0]
            }
            
            return results
            
        except Exception as e:
            print(f"❌ BLIP analysis error: {e}")
            return None
    
    def analyze_with_fashion_vit(self, image_data):
        if self.models['fashion_processor'] is None:
            return None
        
        try:
            image = image_data['person_segmented']
            
            inputs = self.models['fashion_processor'](image, return_tensors="pt")
            
            with torch.no_grad():
                outputs = self.models['fashion_model'](**inputs)
                predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
            
            top_predictions = torch.topk(predictions, 10)
            
            results = {
                'top_classes': [self.models['fashion_model'].config.id2label[idx.item()] 
                              for idx in top_predictions.indices[0]],
                'confidences': top_predictions.values[0].tolist()
            }
            
            return results
            
        except Exception as e:
            print(f"❌ Fashion ViT analysis error: {e}")
            return None
    
    def advanced_color_analysis(self, image_data):
        try:
            image = image_data['person_segmented']
            image_np = np.array(image)
            
            # check if image is valid
            if image_np.size == 0 or len(image_np.shape) != 3:
                print("⚠️ Invalid image for color analysis")
                return {
                    'dominant_colors': [],
                    'pattern_analysis': {'variance': 0, 'pattern_complexity': 'low', 'professional_pattern': True},
                    'professional_color_score': 50,  # neutral score
                    'color_count': 0
                }
            
            # convert to different color formats
            hsv = cv2.cvtColor(image_np, cv2.COLOR_RGB2HSV)
            lab = cv2.cvtColor(image_np, cv2.COLOR_RGB2LAB)
            
            # get pixels and remove background
            pixels = image_np.reshape(-1, 3)
            pixels = pixels[np.sum(pixels, axis=1) > 30]  # remove black background
            
            if len(pixels) == 0:
                print("⚠️ No valid pixels found for color analysis")
                return {
                    'dominant_colors': [],
                    'pattern_analysis': {'variance': 0, 'pattern_complexity': 'low', 'professional_pattern': True},
                    'professional_color_score': 50,
                    'color_count': 0
                }
            
            from sklearn.cluster import KMeans
            
            # find dominant colors using kmeans
            n_colors = min(5, max(1, len(pixels)//100))  # ensure at least 1 color
            kmeans = KMeans(n_clusters=n_colors, random_state=42, n_init=10)
            kmeans.fit(pixels)
            colors = kmeans.cluster_centers_.astype(int)
            
            professional_score = 0
            color_analysis = []
            
            for color in colors:
                r, g, b = color
                
                hsv_color = cv2.cvtColor(np.uint8([[color]]), cv2.COLOR_RGB2HSV)[0][0]
                h, s, v = hsv_color
                
                # check if color is professional looking
                is_professional = False
                color_name = "unknown"
                
                if s < 50:  # low saturation = neutral colors
                    if v < 50:
                        color_name = "black/dark gray"
                        is_professional = True
                        professional_score += 20
                    elif v > 200:
                        color_name = "white/light gray"
                        is_professional = True
                        professional_score += 15
                    else:
                        color_name = "gray"
                        is_professional = True
                        professional_score += 18
                
                # Navy blue
                elif 100 <= h <= 130 and s > 50 and v < 150:
                    color_name = "navy blue"
                    is_professional = True
                    professional_score += 25
                
                # Brown/Tan
                elif 10 <= h <= 25 and s > 30:
                    color_name = "brown/tan"
                    is_professional = True
                    professional_score += 15
                
                # Dark green
                elif 40 <= h <= 80 and s > 30 and v < 120:
                    color_name = "dark green"
                    is_professional = True
                    professional_score += 12
                
                # Burgundy/Wine
                elif (h < 10 or h > 160) and s > 50 and v < 120:
                    color_name = "burgundy/wine"
                    is_professional = True
                    professional_score += 10
                
                # Bright/Neon colors (unprofessional)
                elif s > 200 and v > 200:
                    color_name = "bright/neon"
                    professional_score -= 15
                
                color_analysis.append({
                    'rgb': color.tolist(),
                    'name': color_name,
                    'professional': is_professional,
                    'hsv': hsv_color.tolist()
                })
            
            # Pattern analysis (simplified)
            gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
            
            # Calculate image variance (higher = more patterns)
            variance = np.var(gray)
            
            pattern_analysis = {
                'variance': float(variance),
                'pattern_complexity': 'low' if variance < 500 else 'medium' if variance < 1500 else 'high',
                'professional_pattern': variance < 1000  # Solid colors and simple patterns are more professional
            }
            
            if pattern_analysis['professional_pattern']:
                professional_score += 10
            else:
                professional_score -= 5
            
            return {
                'dominant_colors': color_analysis,
                'pattern_analysis': pattern_analysis,
                'professional_color_score': min(100, max(0, professional_score)),
                'color_count': len(colors)
            }
            
        except Exception as e:
            print(f"❌ Color analysis error: {e}")
            return None
    
    def calculate_comprehensive_score(self, clip_results, blip_results, fashion_results, color_results):
        """Calculate final comprehensive professional score"""
        try:
            score_components = {}
            final_score = 0
            category = "Unknown"
            detailed_feedback = []
            
            # 1. CLIP Analysis (40% weight)
            if clip_results:
                clip_score = 0
                clip_feedback = []
                
                # Analyze full person results
                if 'full_person' in clip_results:
                    best_match = clip_results['full_person']['best_match'].lower()
                    confidence = clip_results['full_person']['confidence']
                    
                    if 'formal business suit' in best_match or 'corporate meeting' in best_match:
                        clip_score = 90 + (confidence * 10)
                        clip_feedback.append("Formal business attire detected")
                    elif 'professional blazer' in best_match or 'business casual' in best_match:
                        clip_score = 75 + (confidence * 15)
                        clip_feedback.append("Professional business casual detected")
                    elif 'smart casual' in best_match:
                        clip_score = 60 + (confidence * 10)
                        clip_feedback.append("Smart casual attire detected")
                    elif 'casual everyday' in best_match:
                        clip_score = 40 - (confidence * 10)
                        clip_feedback.append("Casual attire - not ideal for professional settings")
                    elif 'inappropriate' in best_match:
                        clip_score = 20 - (confidence * 15)
                        clip_feedback.append("Inappropriate attire detected")
                
                score_components['clip'] = {'score': clip_score, 'weight': 0.4, 'feedback': clip_feedback}
                final_score += clip_score * 0.4
            
            # 2. BLIP Analysis (25% weight)
            if blip_results:
                blip_score = 50  # Base score
                blip_feedback = []
                
                description = blip_results['primary_description'].lower()
                
                # Check for professional keywords
                formal_keywords = ['suit', 'tie', 'blazer', 'formal', 'business', 'professional', 'dress shirt']
                casual_keywords = ['t-shirt', 'jeans', 'casual', 'shorts', 'tank', 'athletic']
                
                formal_count = sum(1 for keyword in formal_keywords if keyword in description)
                casual_count = sum(1 for keyword in casual_keywords if keyword in description)
                
                if formal_count > casual_count:
                    blip_score = 70 + (formal_count * 10)
                    blip_feedback.append("Professional clothing elements identified")
                elif casual_count > formal_count:
                    blip_score = 30 - (casual_count * 5)
                    blip_feedback.append("Casual elements detected")
                
                score_components['blip'] = {'score': blip_score, 'weight': 0.25, 'feedback': blip_feedback}
                final_score += blip_score * 0.25
            
            # 3. Color Analysis (20% weight)
            if color_results and isinstance(color_results, dict):
                color_score = color_results.get('professional_color_score', 50)
                color_feedback = []
                
                if color_score >= 80:
                    color_feedback.append("Excellent professional color scheme")
                elif color_score >= 60:
                    color_feedback.append("Good professional colors")
                elif color_score >= 40:
                    color_feedback.append("Acceptable color choices")
                else:
                    color_feedback.append("Colors not ideal for professional settings")
                
                score_components['color'] = {'score': color_score, 'weight': 0.2, 'feedback': color_feedback}
                final_score += color_score * 0.2
            else:
                # fallback if color analysis fails
                print("⚠️ Color analysis failed, using default score")
                score_components['color'] = {'score': 50, 'weight': 0.2, 'feedback': ['Color analysis unavailable']}
                final_score += 50 * 0.2
            
            # 4. Fashion ViT Analysis (15% weight)
            if fashion_results:
                fashion_score = 50
                fashion_feedback = []
                
                # Analyze top predictions for professional items
                professional_items = ['suit', 'blazer', 'dress', 'shirt', 'formal']
                casual_items = ['t-shirt', 'jeans', 'shorts', 'tank']
                
                for i, (class_name, confidence) in enumerate(zip(fashion_results['top_classes'], fashion_results['confidences'])):
                    class_lower = class_name.lower()
                    weight = confidence * (1.0 - i * 0.1)  # Diminishing weight for lower predictions
                    
                    if any(item in class_lower for item in professional_items):
                        fashion_score += weight * 30
                    elif any(item in class_lower for item in casual_items):
                        fashion_score -= weight * 20
                
                fashion_score = max(0, min(100, fashion_score))
                
                if fashion_score >= 70:
                    fashion_feedback.append("Professional clothing items detected")
                else:
                    fashion_feedback.append("Casual clothing items detected")
                
                score_components['fashion'] = {'score': fashion_score, 'weight': 0.15, 'feedback': fashion_feedback}
                final_score += fashion_score * 0.15
            
            # Ensure final score is within bounds
            final_score = max(0, min(100, final_score))
            
            # Determine category and comprehensive feedback
            if final_score >= 85:
                category = "Highly Professional"
                detailed_feedback = ["Outstanding professional attire - perfect for any business setting"]
            elif final_score >= 70:
                category = "Professional"
                detailed_feedback = ["Excellent professional appearance - suitable for most business environments"]
            elif final_score >= 55:
                category = "Business Casual"
                detailed_feedback = ["Good business casual attire - appropriate for casual professional settings"]
            elif final_score >= 40:
                category = "Smart Casual"
                detailed_feedback = ["Smart casual appearance - may be suitable for creative or casual workplaces"]
            elif final_score >= 25:
                category = "Too Casual"
                detailed_feedback = ["Too casual for most professional environments - consider more formal attire"]
            else:
                category = "Inappropriate"
                detailed_feedback = ["Not suitable for professional environments - significant changes needed"]
            
            # Add specific feedback from each component
            for component, data in score_components.items():
                detailed_feedback.extend(data['feedback'])
            
            return {
                'final_score': final_score,
                'category': category,
                'detailed_feedback': detailed_feedback,
                'score_components': score_components,
                'confidence': np.mean([data.get('confidence', 0.5) for data in [clip_results, blip_results] if data])
            }
            
        except Exception as e:
            print(f"❌ Score calculation error: {e}")
            return {
                'final_score': 0,
                'category': 'Error',
                'detailed_feedback': ['Analysis failed'],
                'score_components': {},
                'confidence': 0
            }
    
    def analyze_image(self, image_path, save_results=True):
        """Main function to analyze a single image"""
        print(f"\n🔍 Analyzing: {image_path}")
        start_time = time.time()
        
        try:
            # 1. Preprocess image
            print("📝 Preprocessing image...")
            image_data = self.preprocess_image(image_path)
            
            # 2. Run all analyses
            print("🤖 Running AI analyses...")
            
            clip_results = self.analyze_with_clip(image_data)
            print("  ✅ CLIP analysis complete")
            
            blip_results = self.analyze_with_blip(image_data)
            print("  ✅ BLIP analysis complete")
            
            fashion_results = self.analyze_with_fashion_vit(image_data)
            print("  ✅ Fashion ViT analysis complete")
            
            color_results = self.advanced_color_analysis(image_data)
            print("  ✅ Color analysis complete")
            
            # 3. Calculate comprehensive score
            print("📊 Calculating final score...")
            final_results = self.calculate_comprehensive_score(
                clip_results, blip_results, fashion_results, color_results
            )
            
            # 4. Compile complete results
            complete_results = {
                'image_path': str(image_path),
                'analysis_time': time.time() - start_time,
                'final_assessment': final_results,
                'detailed_analyses': {
                    'clip': clip_results,
                    'blip': blip_results,
                    'fashion_vit': fashion_results,
                    'color_analysis': color_results
                },
                'image_data': {
                    'has_person': image_data.get('pose_landmarks') is not None,
                    'regions_extracted': {
                        'upper_body': image_data.get('upper_body') is not None,
                        'lower_body': image_data.get('lower_body') is not None
                    }
                }
            }
            
            # 5. Save results if requested
            if save_results:
                self.save_analysis_results(complete_results, image_path)
            
            # 6. Display results
            self.display_results(complete_results)
            
            print(f"⏱️  Analysis completed in {complete_results['analysis_time']:.2f} seconds")
            
            return complete_results
            
        except Exception as e:
            print(f"❌ Analysis failed: {e}")
            return None
    
    def save_analysis_results(self, results, image_path):
        """Save detailed analysis results"""
        try:
            output_dir = Path("analysis_results")
            output_dir.mkdir(exist_ok=True)
            
            # Save JSON results
            image_name = Path(image_path).stem
            json_path = output_dir / f"{image_name}_analysis.json"
            
            # Make results JSON serializable
            json_results = self.make_json_serializable(results)
            
            with open(json_path, 'w') as f:
                json.dump(json_results, f, indent=2)
            
            print(f"💾 Results saved to: {json_path}")
            
        except Exception as e:
            print(f"❌ Failed to save results: {e}")
    
    def make_json_serializable(self, obj):
        """Convert numpy arrays and other non-serializable objects to JSON format"""
        if isinstance(obj, dict):
            return {key: self.make_json_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self.make_json_serializable(item) for item in obj]
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, (bool, np.bool_)):
            return bool(obj)
        elif hasattr(obj, '__dict__'):
            return str(obj)
        else:
            return obj
    
    def display_results(self, results):
        """Display comprehensive analysis results"""
        print("\n" + "="*80)
        print("🎯 PROFESSIONAL ATTIRE ANALYSIS RESULTS")
        print("="*80)
        
        final = results['final_assessment']
        
        # Main score and category
        print(f"\n📊 OVERALL SCORE: {final['final_score']:.1f}/100")
        print(f"🏷️  CATEGORY: {final['category']}")
        print(f"🎯 CONFIDENCE: {final['confidence']:.2f}")
        
        # Score breakdown
        print(f"\n📈 SCORE BREAKDOWN:")
        if 'score_components' in final:
            for component, data in final['score_components'].items():
                score = data['score']
                weight = data['weight']
                weighted_score = score * weight
                print(f"  {component.upper()}: {score:.1f}/100 (weight: {weight:.0%}) = {weighted_score:.1f} points")
        
        # Detailed feedback
        print(f"\n💬 DETAILED FEEDBACK:")
        for feedback in final['detailed_feedback']:
            print(f"  • {feedback}")
        
        # Technical details
        if results['detailed_analyses']['blip']:
            print(f"\n🖼️  AI DESCRIPTION:")
            print(f"  {results['detailed_analyses']['blip']['primary_description']}")
        
        if results['detailed_analyses']['color_analysis']:
            color_score = results['detailed_analyses']['color_analysis']['professional_color_score']
            print(f"\n🎨 COLOR ANALYSIS:")
            print(f"  Professional Color Score: {color_score}/100")
            
            colors = results['detailed_analyses']['color_analysis']['dominant_colors']
            professional_colors = [c for c in colors if c['professional']]
            print(f"  Dominant Colors: {len(colors)} total, {len(professional_colors)} professional")
        
        print(f"\n⏱️  Analysis Time: {results['analysis_time']:.2f} seconds")
        print("="*80)

def main():
    """Main function with command line interface"""
    parser = argparse.ArgumentParser(description='Advanced Professional Attire Analysis')
    parser.add_argument('image_path', help='Path to the image file to analyze')
    parser.add_argument('--no-save', action='store_true', help='Do not save analysis results')
    
    args = parser.parse_args()
    
    # Check if image file exists
    if not os.path.exists(args.image_path):
        print(f"❌ Error: Image file '{args.image_path}' not found")
        return
    
    # Initialize analyzer
    analyzer = AdvancedAttireAnalyzer()
    
    # Analyze image
    results = analyzer.analyze_image(args.image_path, save_results=not args.no_save)
    
    if results:
        print(f"\n✅ Analysis complete! Final score: {results['final_assessment']['final_score']:.1f}/100")
    else:
        print("❌ Analysis failed!")

if __name__ == "__main__":
    # If no command line arguments, run in interactive mode
    if len(os.sys.argv) == 1:
        print("🚀 Advanced Attire Analyzer - Interactive Mode")
        print("📝 Enter the path to an image file for analysis:")
        
        image_path = input("Image path: ").strip().strip('"\'')
        
        if os.path.exists(image_path):
            analyzer = AdvancedAttireAnalyzer()
            analyzer.analyze_image(image_path)
        else:
            print(f"❌ Error: Image file '{image_path}' not found")
    else:
        main()
