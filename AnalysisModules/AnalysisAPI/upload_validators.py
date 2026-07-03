import base64
from django.conf import settings

def validate_audio_b64(base64_string):
    """
    Validates a base64 audio string:
    1. Size within limit.
    2. Has valid magic bytes for known audio formats (RIFF/wav, OggS, webm/mkv).
    Returns (is_valid, error_message)
    """
    if not base64_string:
        return False, "Audio data is empty."
        
    # Strip data URL prefix if present
    if base64_string.startswith('data:'):
        if ',' in base64_string:
            base64_string = base64_string.split(',', 1)[1]
            
    # Check estimated size before decoding
    est_bytes = (len(base64_string) * 3) / 4
    max_bytes = getattr(settings, 'MAX_AUDIO_MB', 10) * 1024 * 1024
    
    if est_bytes > max_bytes:
        return False, f"Audio file exceeds maximum allowed size of {getattr(settings, 'MAX_AUDIO_MB', 10)}MB."
        
    try:
        # Decode the first 16 bytes to check magic headers
        header_bytes = base64.b64decode(base64_string[:32])
        
        # Check magic bytes
        # WAV starts with RIFF
        if header_bytes.startswith(b'RIFF'):
            return True, None
            
        # OGG starts with OggS
        if header_bytes.startswith(b'OggS'):
            return True, None
            
        # WEBM / MKV starts with \x1a\x45\xdf\xa3
        if header_bytes.startswith(b'\x1a\x45\xdf\xa3'):
            return True, None
            
        # Add MP3 ID3 header check (often starts with ID3)
        if header_bytes.startswith(b'ID3'):
            return True, None
            
        # Add MP4 / M4A check (starts with ftyp)
        if b'ftyp' in header_bytes[:16]:
            return True, None
            
        # Fallback / relax validation if it decoded successfully but header isn't explicitly recognized 
        # (Whisper can handle many formats, but we want to avoid completely bogus data like images sent as audio)
        # We reject obviously non-audio common formats (like PNG, JPG, PDF)
        if header_bytes.startswith(b'\x89PNG') or header_bytes.startswith(b'\xff\xd8\xff') or header_bytes.startswith(b'%PDF'):
            return False, "Invalid audio format. Detected non-audio file signature."
            
        return True, None
        
    except Exception as e:
        return False, f"Invalid base64 encoding: {str(e)}"

def validate_image_b64(base64_string):
    """
    Validates a base64 image string:
    1. Size within limit.
    2. Has valid magic bytes for JPEG, PNG, WEBP.
    Returns (is_valid, error_message)
    """
    if not base64_string:
        return False, "Image data is empty."
        
    # Strip data URL prefix if present
    if base64_string.startswith('data:'):
        if ',' in base64_string:
            base64_string = base64_string.split(',', 1)[1]
            
    # Check estimated size before decoding
    est_bytes = (len(base64_string) * 3) / 4
    max_bytes = getattr(settings, 'MAX_IMAGE_MB', 2) * 1024 * 1024
    
    if est_bytes > max_bytes:
        return False, f"Image file exceeds maximum allowed size of {getattr(settings, 'MAX_IMAGE_MB', 2)}MB."
        
    try:
        # Decode the first 16 bytes to check magic headers
        header_bytes = base64.b64decode(base64_string[:32])
        
        # Check magic bytes
        # JPEG
        if header_bytes.startswith(b'\xff\xd8\xff'):
            return True, None
            
        # PNG
        if header_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
            return True, None
            
        # WEBP (RIFF ... WEBP)
        if header_bytes.startswith(b'RIFF') and b'WEBP' in header_bytes[:16]:
            return True, None
            
        return False, "Invalid image format. Only JPEG, PNG, and WEBP are allowed."
        
    except Exception as e:
        return False, f"Invalid base64 encoding: {str(e)}"
