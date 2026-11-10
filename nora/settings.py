"""
Django settings for NORA.

The deployment mode (Wikidata or federated Wikibase) is set per ontology, not here.
The AI key belongs to each user and lives in their browser, never in these settings.
"""

import os
from pathlib import Path

from django.utils.translation import gettext_lazy as _
from django.urls import reverse_lazy

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Loads variables from a .env file at the project root (next to manage.py), if present.
# Variables already set in the environment (e.g. by PyCharm or the shell) take precedence.
load_dotenv(BASE_DIR / ".env")


def env_flag(name, default="0"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


DEBUG = env_flag("DJANGO_DEBUG", "1")
HTTPS = env_flag("DJANGO_HTTPS", "0")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off.")
    SECRET_KEY = "development-key-do-not-use-in-production"

ALLOWED_HOSTS = [host.strip() for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")]

INSTALLED_APPS = [
    "whitenoise.runserver_nostatic",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "mapper",
    "social_django",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "social_django.middleware.SocialAuthExceptionMiddleware",
    "mapper.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "nora.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "nora.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentication: Wikimedia OAuth (Meta-Wiki) -------------------------

AUTHENTICATION_BACKENDS = (
    "social_core.backends.mediawiki.MediaWiki",
    "django.contrib.auth.backends.ModelBackend",  # keeps /admin/ login working
)
SOCIAL_AUTH_MEDIAWIKI_KEY = os.environ["OAUTH_KEY"]
SOCIAL_AUTH_MEDIAWIKI_SECRET = os.environ["OAUTH_SECRET"]
SOCIAL_AUTH_MEDIAWIKI_URL = "https://meta.wikimedia.org/w/index.php"
SOCIAL_AUTH_MEDIAWIKI_CALLBACK = os.environ["OAUTH_CALLBACK"]
SOCIAL_AUTH_CLEAN_USERNAMES = False
SOCIAL_AUTH_URL_NAMESPACE = "social"
SOCIAL_AUTH_REDIRECT_IS_HTTPS = HTTPS

LOGIN_URL = "home"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- HTTPS in production (Toolforge terminates TLS at its proxy) ---------

if HTTPS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000

# --- Internationalization -----------------------------------------------

# The interface follows the browser's language when it is one of these;
# otherwise it falls back to LANGUAGE_CODE.
LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", _("English")),
    ("pt-br", _("Brazilian Portuguese")),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# --- Static files ---------------------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]   # your own CSS, images, etc.
STATIC_ROOT = BASE_DIR / "staticfiles"     # where collectstatic gathers everything for production

# --- NORA settings -------------------------------------------------------

# Default endpoint (Wikidata). Ontologies in Wikibase mode use their own
# endpoint, set in the ontology form (see Ontology.api_url).
WIKIDATA_API_ENDPOINT = os.environ.get("WIKIDATA_API_ENDPOINT", "https://www.wikidata.org/w/api.php")

# Wikidata MCP (optional, complementary to the live property search).
# Hosted by Wikimedia Deutschland: https://www.wikidata.org/wiki/Wikidata:MCP
USE_WD_MCP = env_flag("USE_WD_MCP", "0")
WD_MCP_URL = os.environ.get("WD_MCP_URL", "https://wd-mcp.wmcloud.org/mcp/")