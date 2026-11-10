import importlib.util
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

SETTINGS_FILE = Path(__file__).resolve().parents[2] / "nora" / "settings.py"
OAUTH = {"OAUTH_KEY": "key", "OAUTH_SECRET": "secret", "OAUTH_CALLBACK": "callback"}


def load_settings(**env):
    spec = importlib.util.spec_from_file_location("settings_under_test", SETTINGS_FILE)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict("os.environ", {**OAUTH, **env}, clear=True), mock.patch("dotenv.load_dotenv"):
        spec.loader.exec_module(module)
    return module


class SettingsTests(SimpleTestCase):
    def test_production_requires_secret_key(self):
        with self.assertRaises(RuntimeError):
            load_settings(DJANGO_DEBUG="0")

    def test_development_uses_fallback_secret_key(self):
        settings = load_settings()
        self.assertEqual(settings.SECRET_KEY, "development-key-do-not-use-in-production")

    def test_https_turns_on_secure_settings(self):
        settings = load_settings(DJANGO_DEBUG="0", DJANGO_SECRET_KEY="s3cret", DJANGO_HTTPS="1")
        self.assertTrue(settings.SECURE_SSL_REDIRECT)
        self.assertTrue(settings.SESSION_COOKIE_SECURE)
        self.assertTrue(settings.CSRF_COOKIE_SECURE)