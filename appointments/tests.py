from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from patients.models import Patient
from appointments.models import Appointment


class AppointmentWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="adminapt",
            password="StrongPass123",
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            role=User.Role.ADMIN,
            is_approved=True,
            is_active=True,
        )
        self.receptionist = User.objects.create_user(
            username="receptionapt",
            password="StrongPass123",
            first_name="Front",
            last_name="Desk",
            email="front@example.com",
            role=User.Role.RECEPTIONIST,
            is_approved=True,
            is_active=True,
        )
        self.doctor = User.objects.create_user(
            username="doctorapt",
            password="StrongPass123",
            first_name="Doctor",
            last_name="User",
            email="doctor@example.com",
            role=User.Role.DOCTOR,
            is_approved=True,
            is_active=True,
        )
        self.patient = Patient.objects.create(
            full_name="Test Patient",
            date_of_birth="1990-01-01",
            sex=Patient.Sex.MALE,
            phone_number="+263771234567",
            registered_by=self.receptionist,
        )

    def test_receptionist_can_book_future_appointment(self):
        self.client.login(username="receptionapt", password="StrongPass123")
        future = "2099-01-15T09:00:00"
        response = self.client.post(
            reverse("book_appointment"),
            {
                "patient": self.patient.pk,
                "doctor": self.doctor.pk,
                "reason": "Follow-up visit",
                "scheduled_at": future,
                "status": Appointment.Status.SCHEDULED,
                "notes": "Routine check",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Appointment booked.")
        self.assertTrue(Appointment.objects.filter(patient=self.patient, doctor=self.doctor).exists())

    def test_doctor_cannot_book_appointment(self):
        self.client.login(username="doctorapt", password="StrongPass123")
        response = self.client.get(reverse("book_appointment"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=/appointments/book/", response.url)

    def test_cancelled_appointment_requires_reason(self):
        appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            reason="Urgent review",
            scheduled_at="2099-02-15T10:00:00Z",
            status=Appointment.Status.CONFIRMED,
        )
        self.client.login(username="adminapt", password="StrongPass123")
        response = self.client.post(
            reverse("update_appointment_status", args=[appointment.pk, Appointment.Status.CANCELLED]),
            {},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "reason is required")

    def test_doctor_can_view_own_appointments(self):
        Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            reason="Review",
            scheduled_at="2099-03-15T10:00:00Z",
            status=Appointment.Status.CONFIRMED,
        )
        self.client.login(username="doctorapt", password="StrongPass123")
        response = self.client.get(reverse("appointment_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.patient.full_name)
