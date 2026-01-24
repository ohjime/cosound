import os
import socket
import logging
import platform
from pathlib import Path
from dotenv import load_dotenv
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
import dj_database_url


def get_local_ip():
    """Get the local IP address of the machine."""
    try:
        # Create a socket and connect to an external address to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"


LOCAL_IP = get_local_ip()

os.environ["DJANGO_RUNSERVER_HIDE_WARNING"] = "true"
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATHS = [
    BASE_DIR.parent.parent / "env" / ".env",
    BASE_DIR.parent.parent.parent / "env" / ".env",
]
for env_path in ENV_PATHS:
    if env_path.exists():
        load_dotenv(env_path)
        break

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("SECRET_KEY", default="django-insecure-secret-key")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = "RENDER" not in os.environ

ALLOWED_HOSTS = []

if DEBUG:
    ALLOWED_HOSTS.extend(
        [
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "localhost:5173",
            "127.0.0.1:5173",
            "0.0.0.0:5173",
            LOCAL_IP,
            f"{LOCAL_IP}:5173",
        ]
    )
else:
    # Production hosts from env
    prod_hosts = os.environ.get("PROD_HOSTS", "")
    if prod_hosts:
        ALLOWED_HOSTS.extend(prod_hosts.split(","))

# Render provides this environment variable automatically
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# CSRF Configuration for production
CSRF_TRUSTED_ORIGINS = []
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")
    CSRF_TRUSTED_ORIGINS.append(f"https://www.{RENDER_EXTERNAL_HOSTNAME}")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "formatters": {
        "simple": {
            # 1. Add %(asctime)s to the format string
            "format": "[%(asctime)s] %(message)s",
            # 2. (Optional) Define how the date looks
            # This mimics the default Django look (03/Jan/2026 08:24:22)
            "datefmt": "%d/%b/%Y %H:%M:%S",
        },
        "no_timestamp": {
            "format": "%(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "console_no_timestamp": {
            "class": "logging.StreamHandler",
            "formatter": "no_timestamp",
        },
    },
    "loggers": {
        "django.tasks": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "background_task": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "core.tasks": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console_no_timestamp"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "unfold.contrib.import_export",
    "unfold.contrib.guardian",
    "unfold.contrib.simple_history",
    "unfold.contrib.constance",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django_tasks",
    "django_tasks.backends.database",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_vite",
    "django_htmx",
    "django_cotton",
    "widget_tweaks",
    "django_file_form",
    "storages",
    "core",
    "voter",
    "allauth",
    "allauth.account",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": False,
        "OPTIONS": {
            "loaders": [
                [
                    "django.template.loaders.cached.Loader",
                    [
                        "django_cotton.cotton_loader.Loader",
                        "django.template.loaders.filesystem.Loader",
                        "django.template.loaders.app_directories.Loader",
                    ],
                ]
            ],
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
            "builtins": [
                "django_cotton.templatetags.cotton",
            ],
        },
    },
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
WSGI_APPLICATION = "config.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")
AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME")
AWS_S3_SIGNATURE_VERSION = "s3v4"

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Production static files configuration
if not DEBUG:
    STORAGES["staticfiles"] = {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    }

# django-file-form configuration
# S3 direct uploads are enabled by passing s3_upload_dir to the form constructor
# The AWS_* settings are already configured above for django-storages
FILE_FORM_UPLOAD_DIR = "file-form-uploads"
FILE_FORM_MUST_LOGIN = True  # Require authentication for uploads

# Upload size limit - must be >= chunk size (default 2.5MB)
# See: https://mbraak.github.io/django-file-form/details/#production
DATA_UPLOAD_MAX_MEMORY_SIZE = 3 * 1024 * 1024  # 3MB (slightly above 2.5MB chunk size)

# Tell Django to copy static assets into a path called `staticfiles` (for Render)
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_URL = "/static/"
MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/"

STATICFILES_DIRS = [
    BASE_DIR / "vite/static",
]
DJANGO_VITE = {
    "default": {
        "dev_mode": DEBUG,
        "dev_server_host": LOCAL_IP,
        "dev_server_port": 5173,
        "manifest_path": BASE_DIR / "vite/static/manifest.json",
    }
}
AUTH_PASSWORD_VALIDATORS = []
AUTH_USER_MODEL = "core.User"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*"]
ACCOUNT_EMAIL_VERIFICATION = "optional"
ACCOUNT_LOGIN_BY_CODE_ENABLED = True
ACCOUNT_ADAPTER = "voter.adapters.UnifiedLoginAdapter"
ACCOUNT_FORMS = {
    "request_login_code": "voter.adapters.UnifiedRequestLoginCodeForm",
}
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# Database configuration
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("SUPABASE_DB_URL")
    or os.environ.get("SUPABASE_DATABASE_URL")
)
DATABASES = {
    "default": dj_database_url.config(
        # For local development, you can use SQLite or a local PostgreSQL
        default=DATABASE_URL or "sqlite:///" + str(BASE_DIR / "db.sqlite3"),
        conn_max_age=600,
        ssl_require=bool(DATABASE_URL),
    )
}

# Cache configuration
# Use database cache for production (works with multiple gunicorn workers)
# Local-memory cache doesn't work with multi-process servers like gunicorn
# See: https://github.com/mbraak/django-file-form/issues/574
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

TASKS = {
    "default": {
        "BACKEND": "django_tasks.backends.database.DatabaseBackend",
    }
}
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

UNFOLD = {
    "SITE_TITLE": "cosound Manager",
    "SITE_HEADER": "cosound Manager",
    "SIDEBAR": {
        "show_search": True,  # Search in applications and models names
        "command_search": True,  # Replace the sidebar search with the command search
        "show_all_applications": True,  # Dropdown with all applications and models
        "navigation": [
            {
                "title": _("Core Navigation"),
                "separator": True,  # Top border
                "items": [
                    {
                        "title": _("Cosound Players"),
                        "icon": "motion_play",
                        "link": reverse_lazy("admin:core_player_changelist"),
                    },
                    {
                        "title": _("Sound Collection"),
                        "icon": "track_changes",
                        "link": reverse_lazy("admin:core_sound_changelist"),
                    },
                    {
                        "title": _("Player Accounts"),
                        "icon": "apartment",
                        "link": reverse_lazy("admin:core_playeraccount_changelist"),
                    },
                    {
                        "title": _("User Accounts"),
                        "icon": "group",  # Supported icon set: https://fonts.google.com/icons
                        "link": reverse_lazy("admin:core_user_changelist"),
                        "badge_variant": "info",  # info, success, warning, primary, danger
                        "badge_style": "solid",  # background fill style
                        "permission": lambda request: request.user.is_superuser,
                    },
                ],
            },
            {
                "title": _("NFC Voters"),
                "separator": True,  # Top border
                "items": [
                    {
                        "title": _("Registered Voters"),
                        "icon": "how_to_reg",
                        "link": reverse_lazy("admin:voter_voter_changelist"),
                    },
                    {
                        "title": _("Recorded Votes"),
                        "icon": "instant_mix",
                        "link": reverse_lazy("admin:voter_vote_changelist"),
                    },
                ],
            },
        ],
    },
}


COSOUND_SOUND_CLASSIFICATION = "core.classify.RandomSoundClassifier"
COSOUND_SOUND_CLASSIFICATION_DIM = 5
COSOUND_CORE_PREDICTION_FUNCTION = "app.predict.predictor_v1"
