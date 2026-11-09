import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def load_local_env(env_path):
    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env(BASE_DIR / '.env')


def env_bool(nome, padrao=False):
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in {'1', 'true', 'yes', 'on'}


def env_list(nome, padrao=''):
    return [item.strip() for item in os.environ.get(nome, padrao).split(',') if item.strip()]


# Producao por padrao: o modo de desenvolvimento precisa ser ligado
# explicitamente com DJANGO_DEBUG=True (ver .env.example).
DEBUG = env_bool('DJANGO_DEBUG', False)

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('Defina a variavel de ambiente DJANGO_SECRET_KEY em producao.')
    SECRET_KEY = 'django-insecure-chave-apenas-para-desenvolvimento-local'

ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1' if DEBUG else '')
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS')

# O Render informa o dominio publico do servico (ex.: sigpad.onrender.com)
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f'https://{RENDER_EXTERNAL_HOSTNAME}')


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # App do projeto
    'planejamento.apps.PlanejamentoConfig',
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


ROOT_URLCONF = 'planejamento_pcc.urls'


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',

        'DIRS': [
            BASE_DIR / 'templates',
        ],

        'APP_DIRS': True,

        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'planejamento.context_processors.perfil_usuario_logado',
            ],
        },
    },
]


WSGI_APPLICATION = 'planejamento_pcc.wsgi.application'


# Ordem de prioridade:
#   1. DATABASE_URL (Render / producao) -> PostgreSQL
#   2. DJANGO_USE_SQLITE=True -> SQLite (somente com DEBUG=True, desenvolvimento local)
#   3. Variaveis POSTGRES_* (PostgreSQL local, configuracao original do projeto)
DATABASE_URL = os.environ.get('DATABASE_URL')
CONN_MAX_AGE = int(os.environ.get('POSTGRES_CONN_MAX_AGE', '60'))

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=CONN_MAX_AGE,
            conn_health_checks=True,
            ssl_require=env_bool('DATABASE_SSL_REQUIRE', False),
        )
    }
elif env_bool('DJANGO_USE_SQLITE', False):
    if not DEBUG:
        raise ImproperlyConfigured('SQLite so e permitido em desenvolvimento local (DJANGO_DEBUG=True).')
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('POSTGRES_DB', 'planejamento_pcc'),
            'USER': os.environ.get('POSTGRES_USER', 'planejamento_pcc'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'planejamento_pcc'),
            'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
            'PORT': os.environ.get('POSTGRES_PORT', '5432'),
            'CONN_MAX_AGE': CONN_MAX_AGE,
            'OPTIONS': {
                'connect_timeout': int(os.environ.get('POSTGRES_CONNECT_TIMEOUT', '10')),
            },
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'pt-br'

TIME_ZONE = 'America/Bahia'

USE_I18N = True

USE_TZ = True


STATIC_URL = '/static/'

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Arquivos estaticos: WhiteNoise serve /static/ direto pelo Gunicorn.
# Em producao os nomes recebem hash (cache longo) e sao comprimidos.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': (
            'django.contrib.staticfiles.storage.StaticFilesStorage'
            if DEBUG
            else 'whitenoise.storage.CompressedManifestStaticFilesStorage'
        ),
    },
}

# Uploads (anexos de atividades/aulas/conteudos e fotos de perfil).
# O disco do Render e efemero: arquivos enviados se perdem a cada deploy/reinicio.
# Para guardar uploads de forma persistente, configure um bucket compativel com S3
# (AWS S3, Cloudflare R2, Backblaze B2...) com as variaveis abaixo.
AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')
if AWS_STORAGE_BUCKET_NAME:
    STORAGES['default'] = {'BACKEND': 'storages.backends.s3.S3Storage'}
    AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL') or None
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME') or None
    AWS_S3_CUSTOM_DOMAIN = os.environ.get('AWS_S3_CUSTOM_DOMAIN') or None
    AWS_LOCATION = os.environ.get('AWS_LOCATION', 'media')
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = env_bool('AWS_QUERYSTRING_AUTH', True)  # links assinados (bucket privado)
    AWS_S3_FILE_OVERWRITE = False
    # AWS_ACCESS_KEY_ID e AWS_SECRET_ACCESS_KEY sao lidos do ambiente pelo boto3.

# Em producao sem bucket, os uploads podem ser servidos pelo proprio Django
# (DJANGO_SERVE_MEDIA=True), mas continuam temporarios no plano gratuito.
SERVE_MEDIA = DEBUG or (not AWS_STORAGE_BUCKET_NAME and env_bool('DJANGO_SERVE_MEDIA', False))


# Seguranca HTTPS (o Render termina o TLS no proxy e envia X-Forwarded-Proto)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_SECURE_HSTS_SECONDS', '2592000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', False)
    SECURE_HSTS_PRELOAD = env_bool('DJANGO_SECURE_HSTS_PRELOAD', False)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    X_FRAME_OPTIONS = 'DENY'

SESSION_COOKIE_HTTPONLY = True


# Logs no console (aparecem na aba Logs do Render)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'WARNING'},
    'loggers': {
        'django': {'handlers': ['console'], 'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'), 'propagate': False},
    },
}


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'
