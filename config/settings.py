"""Configurações Django do projeto modulos.

Lê variáveis sensíveis do ambiente (via python-decouple) e aplica todas as flags
de segurança quando DEBUG=False. Nunca contém segredos hardcoded.
"""
from __future__ import annotations

import logging
import warnings
from pathlib import Path

import dj_database_url
from decouple import Csv, config

logger = logging.getLogger("modulos.settings")

# ---------------------------------------------------------------------------
# Caminhos base
# ---------------------------------------------------------------------------
# config/settings.py -> parent (config/) -> parent (raiz do projeto = modulos/)
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Segredos e modo de execução
# ---------------------------------------------------------------------------
DEBUG = config("DEBUG", default=False, cast=bool)

SECRET_KEY = config("SECRET_KEY", default="")
if not SECRET_KEY:
    if DEBUG:
        from django.core.management.utils import get_random_secret_key

        SECRET_KEY = get_random_secret_key()
        aviso = (
            "SECRET_KEY ausente: gerada uma chave efêmera apenas para DEBUG. "
            "Defina SECRET_KEY no .env para sessões estáveis."
        )
        warnings.warn(aviso, RuntimeWarning, stacklevel=2)
        logger.warning(aviso)
    else:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(
            "SECRET_KEY é obrigatória em produção (DEBUG=False). "
            "Defina a variável de ambiente SECRET_KEY."
        )

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1" if DEBUG else "",
    cast=Csv(),
)
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

# Prefixo do admin do Django
DJANGO_ADMIN_URL = config("DJANGO_ADMIN_URL", default="admin/")

# Segredos usados pelos módulos
PROSPECTA_FERNET_KEY = config(
    "PROSPECTA_FERNET_KEY",
    default=config("modulos_FERNET_KEY", default=""),
)
GOOGLE_MAPS_API_KEY = config("GOOGLE_MAPS_API_KEY", default="")
GOOGLE_PAGESPEED_API_KEY = config("GOOGLE_PAGESPEED_API_KEY", default="")

# URL base pública do site
SITE_URL = config("SITE_URL", default="http://localhost:8000")

# Prefixos de URL públicos isentos do login admin
PUBLIC_URL_PREFIXES = config(
    "PUBLIC_URL_PREFIXES",
    default="/email-marketing/descadastrar/",
    cast=Csv(),
)

# ---------------------------------------------------------------------------
# Aplicações
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Apps do projeto
    "apps.contas",
    "apps.nucleo",
    # Módulos plugáveis
    "apps.prospeccao",
    "apps.kanban",
    "apps.sla",
    "apps.monitoramento",
    "apps.backup",
    "apps.email_marketing",
    "apps.cupons",
    "apps.blog",
]

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.contas.middleware.InatividadeSessaoMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.contas.middleware.SomenteAdminMiddleware",
    "apps.nucleo.middleware.CabecalhosSegurancaMiddleware",
]

ROOT_URLCONF = "config.urls"

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
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
                "apps.nucleo.context_processors.navegacao",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Banco de dados (dj-database-url)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600 if not DEBUG else 0,
        conn_health_checks=True,
    )
}

# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "contas.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "contas:login"
LOGIN_REDIRECT_URL = "nucleo:dashboard"
LOGOUT_REDIRECT_URL = "contas:login"

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
def _configurar_cache() -> dict:
    backend = config("CACHE_BACKEND", default="locmem").strip().lower()
    if backend in {"db", "database"}:
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.db.DatabaseCache",
                "LOCATION": config("CACHE_TABLE", default="modulos_cache"),
            }
        }
    if backend == "redis":
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": config("REDIS_URL", default="redis://127.0.0.1:6379/1"),
            }
        }
    return {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "modulos-locmem",
        }
    }


CACHES = _configurar_cache()

# ---------------------------------------------------------------------------
# Sessões
# ---------------------------------------------------------------------------
if config("CACHE_BACKEND", default="locmem").strip().lower() == "redis":
    SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
    SESSION_CACHE_ALIAS = "default"
else:
    SESSION_ENGINE = config(
        "SESSION_ENGINE",
        default="django.contrib.sessions.backends.db",
    )

# ---------------------------------------------------------------------------
# Parâmetros de negócio dos módulos
# ---------------------------------------------------------------------------
EMAIL_MARKETING_RATE_LIMIT = config("EMAIL_MARKETING_RATE_LIMIT", default=0, cast=int)
CUSTOMERS_PER_PAGE = config("CUSTOMERS_PER_PAGE", default=20, cast=int)
COUPONS_PER_PAGE = config("COUPONS_PER_PAGE", default=20, cast=int)
CACHE_TTL_DASHBOARD = config("CACHE_TTL_DASHBOARD", default=60, cast=int)

# ---------------------------------------------------------------------------
# Internacionalização
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Arquivos estáticos (WhiteNoise)
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Mídia (uploads) e backups
# ---------------------------------------------------------------------------
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

BACKUPS_DIR = Path(config("BACKUP_DIR", default=str(BASE_DIR / "backups")))

# ---------------------------------------------------------------------------
# Segurança dependente de ambiente
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

SESSAO_INATIVIDADE_SEGUNDOS = config("SESSAO_INATIVIDADE_SEGUNDOS", default=600, cast=int)
SESSION_COOKIE_AGE = SESSAO_INATIVIDADE_SEGUNDOS
SESSION_SAVE_EVERY_REQUEST = False

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = "DENY"

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31_536_000  # 1 ano
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
    SESSION_EXPIRE_AT_BROWSER_CLOSE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "padrao": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "padrao",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "modulos": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}