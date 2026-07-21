import os
import re
import uuid
import hashlib
import logging
from gtts import gTTS
from django.conf import settings

logger = logging.getLogger(__name__)

def clean_text_for_speech(text):
    """
    Cleans markdown formatting and normalizes spaces for TTS.
    """
    if not text:
        return ""
    
    # Remove markdown bold/italic (** or *)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    
    # Remove markdown headers (#, ##)
    text = re.sub(r'#+\s', '', text)
    
    # Replace newlines with spaces for smoother flow
    text = text.replace('\n', ' ')
    
    # Normalize multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def get_or_create_question_audio(text, session_id):
    """
    Takes a question text, hashes it, and checks if audio exists.
    If not, generates it using gTTS and safely moves it to prevent concurrent write collisions.
    Returns the relative URL to the audio file, or None on failure.
    """
    if not text:
        return None
        
    try:
        clean_text = clean_text_for_speech(text)
        if not clean_text:
            return None
            
        # Hash the cleaned text to get a unique identifier
        text_hash = hashlib.md5(clean_text.encode('utf-8')).hexdigest()
        
        # Determine paths
        output_dir = os.path.join(settings.MEDIA_ROOT, 'question_audio')
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"{text_hash}.mp3"
        filepath = os.path.join(output_dir, filename)
        import posixpath
        media_url = settings.MEDIA_URL
        url_path = posixpath.join(media_url, 'question_audio', filename)
        
        # Ensure it starts with a single slash if it's a relative path
        if not url_path.startswith('http') and not url_path.startswith('/'):
            url_path = '/' + url_path
        
        # Fix any accidental double slashes at the start (e.g. //media/ -> /media/)
        if url_path.startswith('//') and not url_path.startswith('//', 2): 
            # if it's exactly two slashes (not 3), and not http://
            url_path = '/' + url_path.lstrip('/')
        
        # Check if it already exists (cache hit)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            logger.info(f"[TTS] Cache hit for question audio: {filename}")
            return url_path
            
        # Generate new audio using temporary file for concurrency safety
        logger.info(f"[TTS] Generating new audio for: {filename}")
        temp_filename = f"temp_{session_id}_{uuid.uuid4().hex[:8]}.mp3"
        temp_filepath = os.path.join(output_dir, temp_filename)
        
        # Generate speech
        tts = gTTS(text=clean_text, lang='en', slow=False)
        tts.save(temp_filepath)
        
        # Atomically rename/replace to avoid race conditions
        # If another worker just saved the exact same file, replace handles it safely.
        os.replace(temp_filepath, filepath)
        
        return url_path
        
    except Exception as e:
        logger.exception(f"[TTS] Failed to generate question audio: {str(e)}")
        # Clean up temp file if it exists and wasn't renamed
        if 'temp_filepath' in locals() and os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath)
            except Exception:
                pass
        return None
