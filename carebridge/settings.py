import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def get_bool_env(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


IS_VERCEL = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV") or BASE_DIR == Path("/var/task"))
DEBUG = get_bool_env("DEBUG", not IS_VERCEL)

_secret_key = (
    os.environ.get("SECRET_KEY")
    or os.environ.get("DJANGO_SECRET_KEY")
    or os.environ.get("VERCEL_SECRET_KEY")
)
if DEBUG:
    SECRET_KEY = _secret_key or "carelink-dev-secret-key-change-me"
else:
    if _secret_key:
        SECRET_KEY = _secret_key
    elif IS_VERCEL:
        # Fallback to allow boot when env var is not configured; sessions/tokens
        # may be unstable across serverless instances. Set SECRET_KEY in Vercel.
        SECRET_KEY = "django-insecure-vercel-" + os.environ.get("VERCEL_DEPLOYMENT_ID", "set-secret-key-in-vercel-env")
    else:
        raise RuntimeError(
            "SECRET_KEY must be set in production. Add it to your environment before starting Django."
        )

_default_hosts = "localhost,127.0.0.1,[::1]"
ALLOWED_HOSTS = [
    host.strip() for host in os.environ.get("ALLOWED_HOSTS", _default_hosts).split(",") if host.strip()
]
if IS_VERCEL:
    ALLOWED_HOSTS.extend([".vercel.app", ".now.sh"])
    for env_name in ("VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
        host = (os.environ.get(env_name) or "").strip()
        if host:
            host = host.replace("https://", "").replace("http://", "").strip("/")
            if host and host not in ALLOWED_HOSTS:
                ALLOWED_HOSTS.append(host)
# de-duplicate while preserving order
ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS))
if not DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()
]
if IS_VERCEL:
    for env_name in ("VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
        host = (os.environ.get(env_name) or "").strip().replace("https://", "").replace("http://", "").strip("/")
        if host:
            origin = f"https://{host}"
            if origin not in CSRF_TRUSTED_ORIGINS:
                CSRF_TRUSTED_ORIGINS.append(origin)
    for origin in ("https://*.vercel.app", "https://*.now.sh"):
        if origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(origin)
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(CSRF_TRUSTED_ORIGINS))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "patients",
    "appointments",
    "laboratory",
    "assistant",
    "billing",
    "core",
    "record_migration",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "carebridge.urls"

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

WSGI_APPLICATION = "carebridge.wsgi.application"

DATABASE_PATH = BASE_DIR / "db.sqlite3"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATABASE_PATH,
    }
}

DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("POSTGRES_URL")
    or os.environ.get("POSTGRES_PRISMA_URL")
)

if DATABASE_URL:
    import dj_database_url

    DATABASES["default"] = dj_database_url.parse(DATABASE_URL, conn_max_age=600)
elif IS_VERCEL:
    # Vercel filesystem is ephemeral; /tmp is writable for boot but not persistent.
    # Configure DATABASE_URL (PostgreSQL) in Vercel for a working deployment.
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "/tmp/carelink.sqlite3",
    }

if IS_VERCEL:
    SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
    CSRF_COOKIE_NAME = "carebridge_csrftoken"
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Harare"
USE_I18N = True
USE_TZ = True

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_ROOT = BASE_DIR / "private_media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

CARELINK_AI_MODEL = os.environ.get("CARELINK_AI_MODEL", "qwen2.5:3b")
CARELINK_OLLAMA_URL = os.environ.get("CARELINK_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
CARELINK_AI_TIMEOUT = int(os.environ.get("CARELINK_AI_TIMEOUT", "20"))
