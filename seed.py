import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "carebridge.settings")
django.setup()

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import User
from appointments.models import Appointment
from billing.models import Invoice
from patients.models import Patient


if not settings.DEBUG or os.environ.get("CARELINK_ALLOW_DEMO_DATA") != "1":
    raise SystemExit("Demo seeding is development-only; enable DEBUG and set CARELINK_ALLOW_DEMO_DATA=1.")

password_variables = {
    "admin": "CARELINK_DEMO_ADMIN_PASSWORD",
    "doctor": "CARELINK_DEMO_DOCTOR_PASSWORD",
    "receptionist": "CARELINK_DEMO_RECEPTIONIST_PASSWORD",
    "pending": "CARELINK_DEMO_PENDING_PASSWORD",
}
demo_passwords = {role: os.environ.get(variable, "") for role, variable in password_variables.items()}
missing_passwords = [variable for role, variable in password_variables.items() if not demo_passwords[role]]
if missing_passwords:
    raise SystemExit("Set separate passwords for all demo roles: " + ", ".join(missing_passwords))
if len(set(demo_passwords.values())) != len(demo_passwords):
    raise SystemExit("Use a different password for each demo role.")


def create_demo_user(username, email, role, password, **attributes):
    existing_user = User.objects.filter(username=username).first()
    if existing_user:
        return existing_user

    user = User(username=username, email=email, role=role, **attributes)
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise SystemExit(f"The password for demo role '{role}' does not meet the configured password policy.") from exc
    user.set_password(password)
    user.save()
    return user


create_demo_user(
    "demo-admin",
    "admin@example.invalid",
    User.Role.ADMIN,
    demo_passwords["admin"],
    first_name="Demo",
    last_name="Administrator",
    is_staff=True,
    is_superuser=True,
    is_active=True,
    is_approved=True,
)
doctor = create_demo_user(
    "demo-doctor",
    "doctor@example.invalid",
    User.Role.DOCTOR,
    demo_passwords["doctor"],
    first_name="Demo",
    last_name="Doctor",
    department="General Medicine",
    staff_id="DEMO-DOCTOR",
    is_approved=True,
)
reception = create_demo_user(
    "demo-reception",
    "reception@example.invalid",
    User.Role.RECEPTIONIST,
    demo_passwords["receptionist"],
    first_name="Demo",
    last_name="Receptionist",
    staff_id="DEMO-RECEPTION",
    is_approved=True,
)
create_demo_user(
    "demo-pending",
    "pending@example.invalid",
    User.Role.DOCTOR,
    demo_passwords["pending"],
    first_name="Demo",
    last_name="Pending",
    department="General Medicine",
    staff_id="DEMO-PENDING",
    is_approved=False,
    is_active=False,
)

patients = []
for full_name, date_of_birth, sex in [
    ("Demo Patient 001", "1990-04-12", Patient.Sex.MALE),
    ("Demo Patient 002", "1985-09-03", Patient.Sex.FEMALE),
    ("Demo Patient 003", "1996-01-20", Patient.Sex.FEMALE),
    ("Demo Patient 004", "1975-11-30", Patient.Sex.FEMALE),
]:
    patient, _created = Patient.objects.get_or_create(
        full_name=full_name,
        defaults={
            "date_of_birth": date_of_birth,
            "sex": sex,
            "registered_by": reception,
        },
    )
    patients.append(patient)

now = timezone.now()
if not Appointment.objects.exists():
    Appointment.objects.create(
        patient=patients[0],
        doctor=doctor,
        reason="Routine consultation",
        scheduled_at=now + timezone.timedelta(hours=1),
        status=Appointment.Status.CONFIRMED,
    )
    Appointment.objects.create(
        patient=patients[1],
        doctor=doctor,
        reason="Follow-up consultation",
        scheduled_at=now + timezone.timedelta(days=1),
        status=Appointment.Status.SCHEDULED,
    )
    Appointment.objects.create(
        patient=patients[2],
        doctor=doctor,
        reason="General consultation",
        scheduled_at=now + timezone.timedelta(days=2),
        status=Appointment.Status.SCHEDULED,
    )

if not Invoice.objects.exists():
    Invoice.objects.create(patient=patients[0], description="Consultation", amount=25, status="PAID")
    Invoice.objects.create(patient=patients[1], description="Administrative demo invoice", amount=15, status="UNPAID")

print("Synthetic demonstration data is ready.")
print("Demo usernames: demo-admin, demo-doctor, demo-reception, demo-pending.")
print("Use the role-specific passwords supplied through environment variables; no passwords are printed.")
