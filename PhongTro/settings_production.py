"""
Production settings for PythonAnywhere deployment
"""
from .settings import *
import os

# SECURITY
DEBUG = False
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', SECRET_KEY)

# PythonAnywhere domain - Thay đổi USERNAME thành tên user của bạn
ALLOWED_HOSTS = [
    'USERNAME.pythonanywhere.com',  # ⚠️ THAY ĐỔI USERNAME
    '127.0.0.1',
    'localhost'
]

# Database - PythonAnywhere hỗ trợ PostgreSQL/MySQL
# Free tier: MySQL
# Paid tier: PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',  # Hoặc postgresql cho paid plan
        'NAME': 'USERNAME$phongtro',  # ⚠️ THAY ĐỔI USERNAME
        'USER': 'USERNAME',  # ⚠️ THAY ĐỔI USERNAME
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),  # Đặt trong .env
        'HOST': 'USERNAME.mysql.pythonanywhere-services.com',  # ⚠️ THAY ĐỔI USERNAME
        'PORT': '3306',
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        }
    }
}

# Static files - Dùng WhiteNoise
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATIC_URL = '/static/'

# Media files
MEDIA_ROOT = '/home/USERNAME/phongtro/media'  # ⚠️ THAY ĐỔI USERNAME
MEDIA_URL = '/media/'

# Email - Nên dùng environment variable
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')

# Site URL - Thay đổi sau khi deploy
SITE_URL = 'https://USERNAME.pythonanywhere.com'  # ⚠️ THAY ĐỔI USERNAME

# MoMo callback URLs
MOMO_NOTIFY_URL = SITE_URL + '/payments/momo/notify/'
MOMO_RETURN_URL = SITE_URL + '/payments/momo/return/'

# VNPAY callback URLs
VNPAY_RETURN_URL = SITE_URL + '/payments/vnpay/return/'
VNPAY_NOTIFY_URL = SITE_URL + '/payments/vnpay/notify/'

# Channels - PythonAnywhere không hỗ trợ WebSocket trực tiếp
# Nếu cần WebSocket, phải dùng external service hoặc upgrade plan
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# Security headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Session security
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': '/home/USERNAME/phongtro/logs/django.log',  # ⚠️ THAY ĐỔI USERNAME
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
}
