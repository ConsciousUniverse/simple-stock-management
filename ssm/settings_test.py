"""
Settings used by the automated test suite (pytest).

The base settings module reads its configuration from environment
variables (populated from a local .env file).  To make the test run
deterministic and independent of any developer's local .env, the values
below are force-set *before* the base settings are imported.  python-dotenv
does not override variables that already exist in the environment, so
these values always win.
"""

import os
import tempfile

os.environ.update(
    {
        "DJANGO_SECRET_KEY": "insecure-test-secret-key",
        "DJANGO_DEBUG": "False",
        "DJANGO_ALLOWED_HOSTS": "testserver,127.0.0.1,localhost",
        "DB_NAME": "db.sqlite3",  # unused: Django runs SQLite tests in memory
        "ALLOW_PW_CHANGE": "True",
        "AXES_FAILURE_LIMIT": "3",
        "AXES_COOLOFF_TIME": "1",
        "MAIL_SERVICE_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
        "MAIL_SERVICE_API_KEY": "",
        "MAIL_SERVICE_API_URL": "",
        "MAIL_DEFAULT_FROM": "ssm-test@example.com",
        "MAIL_SERVER_EMAIL": "ssm-test@example.com",
        "LOG_FILE": os.devnull,
    }
)

from .settings import *  # noqa: E402,F401,F403
from .settings import DATABASES, REST_FRAMEWORK  # noqa: E402

# Use a file-backed test database rather than SQLite's default in-memory
# one: the Playwright end-to-end tests run a live server in a separate
# thread, and a shared-cache in-memory SQLite database is not reliable
# across threads (it can crash the interpreter mid-suite). The file is
# created and destroyed by the test runner.
DATABASES["default"]["TEST"] = {
    "NAME": os.path.join(tempfile.gettempdir(), "ssm_test_db.sqlite3"),
}

# Fast password hashing: login-heavy tests would otherwise spend most of
# their time in PBKDF2.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Captured in django.core.mail.outbox instead of hitting a mail provider.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Throttle counters live in the per-process cache and would leak between
# tests, so throttling is switched off for the suite.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {},
}

# django-axes interferes with the test client's login helpers, so it is
# disabled globally; the dedicated lockout tests re-enable it with
# override_settings.
AXES_ENABLED = False

# The test client and the Playwright live server both run over plain HTTP, so
# the production HTTPS-only cookie/redirect settings are switched off here.
# The production wiring itself is asserted against the base settings module.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0

# Console-only logging: the suite must never depend on a writable log file.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "level": "WARNING",
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
