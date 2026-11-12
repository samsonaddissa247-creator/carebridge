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


def _bootstrap_admin():
    """Optionally create an initial admin when env vars are provided.

    Useful for fresh/ephemeral deployments where no shell access is available.
    """
    username = (os.environ.get("CARELINK_ADMIN_USERNAME") or "").strip()
    password = os.environ.get("CARELINK_ADMIN_PASSWORD") or ""
    if not username or not password:
        return
    try:
        from accounts.models import User

        email = (os.environ.get("CARELINK_ADMIN_EMAIL") or "").strip()
        staff_id = (os.environ.get("CARELINK_ADMIN_STAFF_ID") or "ADMIN-001").strip() or "ADMIN-001"
        user = User.objects.filter(username=username).first()
        if user:
            changed = False
            if getattr(user, "role", None) != User.Role.ADMIN:
                user.role = User.Role.ADMIN
                changed = True
            if not user.is_active:
                user.is_active = True
                changed = True
            if not user.is_staff:
                user.is_staff = True
                changed = True
            if hasattr(user, "is_approved") and not user.is_approved:
                user.is_approved = True
                changed = True
            if changed:
                user.save()
            return
        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            role=User.Role.ADMIN,
            is_active=True,
            is_approved=True,
            staff_id=staff_id,
        )
    except Exception:
        # Do not block boot; admin can be created manually once DB is ready.
        pass


_auto_migrate()
_bootstrap_admin()

from carebridge.wsgi import application  # noqa: E402

app = application
