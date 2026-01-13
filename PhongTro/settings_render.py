"""
Production settings for Render.com deployment
"""
from .settings import *
import os
import dj_database_url

# SECURITY
DEBUG = False
SECRET_KEY = os.environ.get('SECRET_KEY', SECRET_KEY)

# Remove heavy apps for Render free tier (chatbot needs torch/numpy)
# Keep goiy_ai for models only (PostView, UserInteraction)
INSTALLED_APPS = [app for app in INSTALLED_APPS if app not in ['chatbot']]

# Disable chatbot URLs in production
ROOT_URLCONF = 'PhongTro.urls_render'

# Render.com provides RENDER_EXTERNAL_HOSTNAME
ALLOWED_HOSTS = [
    os.environ.get('RENDER_EXTERNAL_HOSTNAME', ''),
    '127.0.0.1',
    'localhost'
]

if os.environ.get('RENDER_EXTERNAL_HOSTNAME'):
    ALLOWED_HOSTS.append(os.environ['RENDER_EXTERNAL_HOSTNAME'])

# Database - Render tự động cung cấp DATABASE_URL
DATABASES = {
    'default': dj_database_url.config(
        default='postgresql://postgres:postgres@localhost:5432/phongtro',
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Static files - WhiteNoise
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATIC_URL = '/static/'

# Media files
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_URL = '/media/'

# Email
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')

if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = 'smtp.gmail.com'
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Site URL
SITE_URL = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')}"

# Payment callbacks
MOMO_NOTIFY_URL = SITE_URL + '/payments/momo/notify/'
MOMO_RETURN_URL = SITE_URL + '/payments/momo/return/'
VNPAY_RETURN_URL = SITE_URL + '/payments/vnpay/return/'
VNPAY_NOTIFY_URL = SITE_URL + '/payments/vnpay/notify/'

# Channels - Render hỗ trợ WebSocket!
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# Security headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}
