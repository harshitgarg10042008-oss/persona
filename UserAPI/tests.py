import importlib
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AuthSessionTests(TestCase):
    def test_secret_key_is_persisted_between_reloads(self):
        from PersonaBackend import settings as settings_module

        secret_key_path = Path(settings_module.BASE_DIR) / '.secret_key'
        if secret_key_path.exists():
            secret_key_path.unlink()

        os.environ.pop('SECRET_KEY', None)

        reloaded_settings = importlib.reload(settings_module)
        first_key = reloaded_settings.SECRET_KEY

        reloaded_settings = importlib.reload(settings_module)
        second_key = reloaded_settings.SECRET_KEY

        self.assertEqual(first_key, second_key)
        self.assertTrue(secret_key_path.exists())

    def test_remember_me_sets_longer_session_expiry(self):
        user = get_user_model().objects.create_user(
            username='remember@example.com',
            email='remember@example.com',
            password='StrongPass123',
        )

        response = self.client.post(
            reverse('login'),
            {
                'username': 'remember@example.com',
                'password': 'StrongPass123',
                'remember_me': 'on',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertGreaterEqual(self.client.session.get_expiry_age(), 60 * 60 * 24 * 20)
