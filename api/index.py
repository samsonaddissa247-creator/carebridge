import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "carebridge.settings")

import django

django.setup()

from django.conf import settings
from django.core.management import call_command


def _auto_migrate():
    """Apply migrations on serverless/ephemeral environments so auth/login can work."""
    db = settings.DATABASES.get("default", {})
    engine = db.get("ENGINE", "")
    name = str(db.get("NAME", ""))
    is_ephemeral_sqlite = "sqlite3" in engine and (
        name.startswith("/tmp") or getattr(settings, "IS_VERCEL", False)
    )
    # Always try on ephemeral sqlite; also try when explicitly requested.
    should_migrate = is_ephemeral_sqlite or os.environ.get("CARELINK_AUTO_MIGRATE", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not should_migrate:
        return
    try:
        call_command("migrate", interactive=False, verbosity=0)
    except Exception:
        # Do not crash import; the underlying DB/config issue will surface on request.
        pass


_auto_migrate()

from carebridge.wsgi import application  # noqa: E402

app = application
