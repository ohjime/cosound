import os
import logging
import platform
from pathlib import Path
from dotenv import load_dotenv
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _


os.environ["DJANGO_RUNSERVER_HIDE_WARNING"] = "true"
BASE_DIR = Path(__file__).resolve().parent.parent.parent
SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-secret-key")
DEBUG = os.getenv("DEBUG", "True") == "True"
load_dotenv(BASE_DIR.parent.parent / "env" / ".env")
if DEBUG:
    ALLOWED_HOSTS = str(os.getenv("DEV_HOSTS", default=["*"])).split(",")
else:
    ALLOWED_HOSTS = str(os.getenv("PROD_HOSTS", default=["*"])).split(",")
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
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
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
        "app.tasks": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console"],
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
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_vite",
    "django_htmx",
    "django_cotton",
    "widget_tweaks",
    "django_file_form",
    "storages",
    "users",
    "app",
    "allauth",
    "allauth.account",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]
ROOT_URLCONF = "main.urls"
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
WSGI_APPLICATION = "main.wsgi.application"
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

# django-file-form S3 upload configuration
FILE_FORM_UPLOAD_DIR = "file-form-uploads"

STATIC_ROOT = BASE_DIR / "static"
STATIC_URL = "static/"
MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/"

STATICFILES_DIRS = [
    BASE_DIR / "vite/static",
]
DJANGO_VITE = {
    "default": {
        "dev_mode": DEBUG,
        "dev_server_host": "10.0.0.57",
        "dev_server_port": 5173,
    }
}
AUTH_PASSWORD_VALIDATORS = []
AUTH_USER_MODEL = "users.User"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*"]
ACCOUNT_EMAIL_VERIFICATION = "optional"
ACCOUNT_LOGIN_BY_CODE_ENABLED = True
ACCOUNT_ADAPTER = "users.adapters.UnifiedLoginAdapter"
ACCOUNT_FORMS = {
    "request_login_code": "users.adapters.UnifiedRequestLoginCodeForm",
}
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
TASKS = {
    "default": {
        "BACKEND": "django.tasks.backends.immediate.ImmediateBackend",
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
                "title": _("Navigation"),
                "separator": True,  # Top border
                "items": [
                    {
                        "title": _("Generated Cosounds"),
                        "icon": "instant_mix",  # Supported icon set: https://fonts.google.com/icons
                        "link": reverse_lazy("admin:app_cosound_changelist"),
                        "badge_variant": "info",  # info, success, warning, primary, danger
                        "badge_style": "solid",  # background fill style
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": _("Registered Players"),
                        "icon": "motion_play",
                        "link": reverse_lazy("admin:app_player_changelist"),
                    },
                    {
                        "title": _("Sound Library"),
                        "icon": "track_changes",
                        "link": reverse_lazy("admin:app_sound_changelist"),
                    },
                ],
            },
            {
                "title": _("Users & Roles"),
                "separator": True,  # Top border
                # "collapsible": True,  # Collapsible group of links
                "items": [
                    {
                        "title": _("User Accounts"),
                        "icon": "group",  # Supported icon set: https://fonts.google.com/icons
                        "link": reverse_lazy("admin:users_user_changelist"),
                        "badge_variant": "info",  # info, success, warning, primary, danger
                        "badge_style": "solid",  # background fill style
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": _("Registered Clients"),
                        "icon": "apartment",
                        "link": reverse_lazy("admin:users_client_changelist"),
                    },
                    {
                        "title": _("Captured Voters"),
                        "icon": "how_to_reg",
                        "link": reverse_lazy("admin:users_voter_changelist"),
                    },
                ],
            },
        ],
    },
}
