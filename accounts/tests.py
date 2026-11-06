from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from patients.models import Patient


class CareLinkSecurityTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="adminsec",
            password="StrongPass123",
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            role=User.Role.ADMIN,
            is_approved=True,
            is_active=True,
        )
        self.receptionist = User.objects.create_user(
            username="receptionsec",
            password="StrongPass123",
            first_name="Front",
            last_name="Desk",
            email="front@example.com",
            role=User.Role.RECEPTIONIST,
            is_approved=True,
            is_active=True,
        )
        self.doctor = User.objects.create_user(
            username="doctorsec",
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

    def test_admin_login_success(self):
        response = self.client.post(
            reverse("login"),
            {"username": "adminsec", "password": "StrongPass123"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse("dashboard"))

    def test_pending_staff_cannot_login(self):
        User.objects.create_user(
            username="pendingdoctor",
            password="StrongPass123",
            first_name="Pending",
            last_name="Doctor",
            email="pending@example.com",
            role=User.Role.DOCTOR,
            is_approved=False,
            is_active=True,
        )
        response = self.client.post(
            reverse("login"),
            {"username": "pendingdoctor", "password": "StrongPass123"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pending approval")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_doctor_cannot_access_patient_registration(self):
        self.client.login(username="doctorsec", password="StrongPass123")
        response = self.client.get(reverse("register_patient"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=/patients/register/", response.url)

    def test_receptionist_can_access_patient_detail(self):
        self.client.login(username="receptionsec", password="StrongPass123")
        response = self.client.get(reverse("patient_detail", args=[self.patient.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.patient.full_name)

    def test_doctor_can_view_patient_detail(self):
        self.client.login(username="doctorsec", password="StrongPass123")
        response = self.client.get(reverse("patient_detail", args=[self.patient.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.patient.full_name)
