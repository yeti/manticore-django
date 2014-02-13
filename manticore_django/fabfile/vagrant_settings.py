__author__ = 'rudy'

DATABASES = {
    "default": {
        # Ends with "postgresql_psycopg2", "mysql", "sqlite3" or "oracle".
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        # DB name or path to database file if using sqlite3.
        "NAME": "%(proj_name)s",
        # Not used with sqlite3.
        "USER": "%(proj_name)s",
        # Not used with sqlite3.
        "PASSWORD": "%(db_pass)s",
        # Set to empty string for localhost. Not used with sqlite3.
        "HOST": "%(primary_database_host)s",
        # Set to empty string for default. Not used with sqlite3.
        "PORT": "",
    }
}

# Mezzanine settings
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTOCOL", "https")

CACHE_MIDDLEWARE_SECONDS = 60

CACHE_MIDDLEWARE_KEY_PREFIX = "%(proj_name)s"

# Caches are disabled for vagrant.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Since Vagrant is running on your computer, you can turn on debugging.
DEBUG = True

# SESSION_ENGINE = "django.contrib.sessions.backends.cache"

# Django 1.5+ requires a set of allowed hosts
ALLOWED_HOSTS = ["127.0.0.1", "0.0.0.0"]

# Celery configuration (if django-celery is installed in requirements/requirements.txt)
BROKER_URL = 'amqp://%(proj_name)s:%(admin_pass)s@127.0.0.1:5672/%(proj_name)s'

# We don't need to report any crashes to an outside server.
RAVEN_CONFIG = {}

DEBUG = True

SECRET_KEY = "1234"
NEVERCACHE_KEY = "1234"