import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "carebridge.settings")
django.setup()

from django.utils import timezone
from accounts.models import User
from patients.models import Patient
from appointments.models import Appointment
from billing.models import Invoice

# --- Users ---
if not User.objects.filter(username="admin").exists():
    admin = User.objects.create_superuser(
        username="admin", password="admin123", email="admin@carebridge.zw",
        first_name="Memory", last_name="Chikuni", role=User.Role.ADMIN, is_approved=True,
    )
else:
    admin = User.objects.get(username="admin")

if not User.objects.filter(username="drncube").exists():
    doctor = User.objects.create_user(
        username="drncube", password="doctor123", email="ncube@carebridge.zw",
        first_name="Tanaka", last_name="Ncube", role=User.Role.DOCTOR,
        department="General Medicine", staff_id="STF-1001", is_approved=True,
    )
else:
    doctor = User.objects.get(username="drncube")

if not User.objects.filter(username="reception1").exists():
    reception = User.objects.create_user(
        username="reception1", password="front123", email="front@carebridge.zw",
        first_name="Sipho", last_name="Ndlovu", role=User.Role.RECEPTIONIST,
        staff_id="STF-2001", is_approved=True,
    )
else:
    reception = User.objects.get(username="reception1")

if not User.objects.filter(username="drpending").exists():
    User.objects.create_user(
        username="drpending", password="pending123", email="pending@carebridge.zw",
        first_name="Blessing", last_name="Gumbo", role=User.Role.DOCTOR,
        department="Maternity", staff_id="STF-1050", is_approved=False, is_active=False,
    )

# --- Patients ---
patients_data = [
    ("Tendai Moyo", "1990-04-12", "M", "+263771234567"),
    ("Rutendo Sibanda", "1985-09-03", "F", "+263772345678"),
    ("Panashe Mutasa", "1996-01-20", "F", "+263773456789"),
    ("Lindiwe Chuma", "1975-11-30", "F", "+263774567890"),
]
patients = []
for name, dob, sex, phone in patients_data:
    p, _ = Patient.objects.get_or_create(
        full_name=name, defaults=dict(date_of_birth=dob, sex=sex, phone_number=phone, registered_by=reception)
    )
    patients.append(p)

# --- Appointments ---
now = timezone.now()
if not Appointment.objects.exists():
    Appointment.objects.create(patient=patients[0], doctor=doctor, reason="Chest pain",
                                scheduled_at=now.replace(hour=9, minute=0), status="CONFIRMED")
    Appointment.objects.create(patient=patients[1], doctor=doctor, reason="Follow-up",
                                scheduled_at=now.replace(hour=10, minute=30), status="PENDING")
    Appointment.objects.create(patient=patients[2], doctor=doctor, reason="Antenatal check",
                                scheduled_at=now + timezone.timedelta(days=1), status="PENDING")

# --- Invoices ---
if not Invoice.objects.exists():
    Invoice.objects.create(patient=patients[0], description="Consultation", amount=25, status="PAID")
    Invoice.objects.create(patient=patients[1], description="Lab test - Malaria", amount=15, status="UNPAID")

print("Seed data created.")
print("Login as: admin/admin123 (Admin) | drncube/doctor123 (Doctor) | reception1/front123 (Receptionist)")
print("Pending approval demo account: drpending/pending123")
