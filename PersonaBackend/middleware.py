from django.conf import settings
from django.http import HttpResponse, JsonResponse
import json

class RequestSizeLimitMiddleware:
    """
    Middleware to prevent large payloads from being processed.
    Limits request sizes based on settings.MAX_AUDIO_MB and MAX_IMAGE_MB.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.max_audio_bytes = getattr(settings, 'MAX_AUDIO_MB', 10) * 1024 * 1024
        self.max_image_bytes = getattr(settings, 'MAX_IMAGE_MB', 2) * 1024 * 1024
        # We'll use the larger limit for the overall request payload size guard
        self.max_payload_bytes = max(self.max_audio_bytes, self.max_image_bytes)

    def __call__(self, request):
        if request.method in ('POST', 'PUT', 'PATCH'):
            content_length = request.META.get('CONTENT_LENGTH')
            if content_length:
                try:
                    content_length = int(content_length)
                    if content_length > self.max_payload_bytes:
                        if request.headers.get('content-type', '').startswith('application/json') or request.headers.get('x-requested-with') == 'XMLHttpRequest':
                            return JsonResponse(
                                {'error': 'Payload Too Large'}, 
                                status=413
                            )
                        return HttpResponse('Payload Too Large', status=413)
                except ValueError:
                    pass
                    
        return self.get_response(request)

class SecurityHeadersMiddleware:
    """
    Adds Permissions-Policy and Referrer-Policy headers.
    X-Frame-Options, X-Content-Type-Options, and CSP are handled by Django 
    and django-csp built-ins.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Limit what browser features the app can use.
        response['Permissions-Policy'] = 'camera=self, microphone=self, geolocation=()'
        
        # Limit referer info sent to other sites.
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        return response
