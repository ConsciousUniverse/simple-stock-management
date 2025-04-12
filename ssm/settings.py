from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()


def get_bool_env(var_name):
    return var_name.lower() in ("true", "1", "yes", "on")


BASE_DIR = Path(__file__).resolve().parent.parent
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = get_bool_env(os.getenv("DJANGO_DEBUG"))
ALLOWED_HOSTS = [
    host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",")
]
ALLOW_PW_CHANGE = get_bool_env(os.getenv("ALLOW_PW_CHANGE"))
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "stock_manager",
    "axes",
    "email_service.apps.EmailServiceConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]
AXES_FAILURE_LIMIT = int(os.getenv("AXES_FAILURE_LIMIT"))
AXES_COOLOFF_TIME = int(os.getenv("AXES_COOLOFF_TIME"))
AXES_LOCKOUT_PARAMETERS = ["username"]
AXES_CLIENT_IP_CALLABLE = lambda x: None  # Disable logging IP
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "100/day", "user": "100/second"},
    "DEFAULT_PAGINATION_CLASS": "stock_manager.pagination.CustomPagination",
}
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"
ROOT_URLCONF = "ssm.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
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
SEND_NOTIFICATION_EMAIL = get_bool_env(os.getenv("MAIL_SEND_NOTIFICATIONS"))
EMAIL_BACKEND = os.getenv("MAIL_SERVICE_BACKEND")
DEFAULT_FROM_EMAIL = os.getenv("MAIL_DEFAULT_FROM")
SERVER_EMAIL = os.getenv("MAIL_SERVER_EMAIL")
ALLOW_UPLOADS = get_bool_env(os.getenv("ALLOW_UPLOADS"))
ALLOW_RECORD_DELETE_FROM_XLSX = get_bool_env(os.getenv("ALLOW_RECORD_DELETE_FROM_XLSX"))
ANYMAIL = {
    "IGNORE_UNSUPPORTED_FEATURES": True,
    "SPARKPOST_API_KEY": os.getenv("MAIL_SERVICE_API_KEY"),
    "SPARKPOST_API_URL": os.getenv("MAIL_SERVICE_API_URL"),
}
WSGI_APPLICATION = "ssm.wsgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / os.environ.get("DB_NAME"),
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "static")
MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")
LOG_FILE = os.getenv("LOG_FILE")  # this directory & file needs to be created first!
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s"
        },
        "simple": {"format": "%(asctime)s %(levelname)s %(message)s"},
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filename": LOG_FILE,
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
