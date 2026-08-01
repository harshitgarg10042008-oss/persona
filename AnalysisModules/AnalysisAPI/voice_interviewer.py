import os
import uuid
import hashlib
import logging
import asyncio
from django.conf import settings

logger = logging.getLogger(__name__)

# Available interviewer personas matching edge-tts voices
PERSONAS = {
    'professional_stern': {
        'id': 'professional_stern',
        'name': 'Professional & Stern',
        'voice': 'en-US-ChristopherNeural',  # deep, authoritative male voice
        'description': 'Direct, analytical, and maintains a strict professional boundary.',
        'avatar': '/static/avatars/professional_stern.png',
    },
    'friendly_encouraging': {
        'id': 'friendly_encouraging',
        'name': 'Friendly & Encouraging',
        'voice': 'en-US-AriaNeural',         # warm, friendly female voice
        'description': 'Supportive, patient, and creates a welcoming atmosphere.',
        'avatar': '/static/avatars/friendly_encouraging.png',
    },
    'analytical_direct': {
        'id': 'analytical_direct',
        'name': 'Analytical & Direct',
        'voice': 'en-GB-SoniaNeural',        # crisp, precise British female voice
        'description': 'Focuses on details, speaks clearly and expects precise answers.',
        'avatar': '/static/avatars/analytical_direct.png',
    }
}

# Default avatar shown when a persona has no avatar configured
DEFAULT_AVATAR = '/static/avatars/default_interviewer.png'

def get_persona_avatar(persona_id):
    """
    Returns the avatar URL for a persona. Falls back to DEFAULT_AVATAR
    if the persona is not found or has no avatar configured.
    """
    persona = PERSONAS.get(persona_id)
    if not persona:
        return DEFAULT_AVATAR
    return persona.get('avatar', DEFAULT_AVATAR)

def get_default_persona():
    return 'friendly_encouraging'

def clean_text_for_speech(text):
    """
    Cleans markdown formatting and normalizes spaces for TTS.
    """
    if not text:
        return ""
    
    import re
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

async def _generate_audio_async(text, voice, filepath):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(filepath)

def generate_question_audio(text, persona_id, session_id):
    """
    Takes a question text, hashes it along with the persona, and checks if audio exists.
    If not, generates it using edge-tts.
    Returns the relative URL to the audio file, or None on failure.
    """
    if not text:
        return None
        
    try:
        clean_text = clean_text_for_speech(text)
        if not clean_text:
            return None
            
        persona = PERSONAS.get(persona_id)
        if not persona:
            logger.warning(f"Persona {persona_id} not found, falling back to default.")
            persona = PERSONAS[get_default_persona()]
            
        voice = persona['voice']
        
        # Hash the cleaned text + persona to get a unique identifier
        hash_input = f"{clean_text}_{voice}"
        text_hash = hashlib.md5(hash_input.encode('utf-8')).hexdigest()
        
        # Determine paths
        output_dir = os.path.join(settings.MEDIA_ROOT, 'question_audio')
        # Use isdir check first to avoid PermissionError on OneDrive-synced dirs
        if not os.path.isdir(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
            except PermissionError:
                # OneDrive may lock the directory on Windows — if it already exists, proceed
                if not os.path.isdir(output_dir):
                    raise
        
        filename = f"{text_hash}.mp3"
        filepath = os.path.join(output_dir, filename)
        
        import posixpath
        media_url = settings.MEDIA_URL
        url_path = posixpath.join(media_url, 'question_audio', filename)
        
        if not url_path.startswith('http') and not url_path.startswith('/'):
            url_path = '/' + url_path
            
        if url_path.startswith('//') and not url_path.startswith('//', 2): 
            url_path = '/' + url_path.lstrip('/')
        
        # Check if it already exists (cache hit)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            logger.info(f"[TTS] Cache hit for question audio: {filename} (Persona: {persona['name']})")
            return url_path
            
        # Generate new audio using temporary file for concurrency safety
        logger.info(f"[TTS] Generating new audio for: {filename} (Persona: {persona['name']})")
        temp_filename = f"temp_{session_id}_{uuid.uuid4().hex[:8]}.mp3"
        temp_filepath = os.path.join(output_dir, temp_filename)
        
        # Generate speech synchronously — asyncio.run() creates its own loop safely
        asyncio.run(_generate_audio_async(clean_text, voice, temp_filepath))
        
        # Atomically rename/replace to avoid race conditions
        os.replace(temp_filepath, filepath)
        
        return url_path
        
    except Exception as e:
        logger.exception(f"[TTS] Failed to generate question audio: {str(e)}")
        if 'temp_filepath' in locals() and os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath)
            except Exception:
                pass
        return None
