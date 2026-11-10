from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from accounts.forms import StaffRegistrationRequestForm
from appointments.models import QueueEntry
from patients.models import Patient


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
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
            allergies="Private allergy detail",
            chronic_conditions="Private condition detail",
            notes="Private patient note",
            registered_by=self.receptionist,
        )
        QueueEntry.objects.create(
            patient=self.patient,
            assigned_doctor=self.doctor,
            queue_number="Q-SECURITY-1",
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

    def test_unassigned_doctor_cannot_view_patient_detail(self):
        other_patient = Patient.objects.create(
            full_name="Unassigned Synthetic Patient",
            date_of_birth="1991-02-03",
            sex=Patient.Sex.FEMALE,
            registered_by=self.receptionist,
        )
        self.client.force_login(self.doctor)
        response = self.client.get(reverse("patient_detail", args=[other_patient.pk]))
        self.assertEqual(response.status_code, 404)

    def test_receptionist_patient_detail_hides_clinical_information(self):
        self.client.force_login(self.receptionist)
        response = self.client.get(reverse("patient_detail", args=[self.patient.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Private allergy detail")
        self.assertNotContains(response, "Private condition detail")
        self.assertNotContains(response, "Private patient note")

    def test_receptionist_registration_form_omits_clinical_fields(self):
        self.client.force_login(self.receptionist)
        response = self.client.get(reverse("register_patient"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="allergies"')
        self.assertNotContains(response, 'name="chronic_conditions"')
        self.assertNotContains(response, 'name="notes"')

    def test_doctor_can_view_patient_detail(self):
        self.client.login(username="doctorsec", password="StrongPass123")
        response = self.client.get(reverse("patient_detail", args=[self.patient.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.patient.full_name)

    def test_doctor_patient_list_contains_only_assigned_patients(self):
        other_patient = Patient.objects.create(
            full_name="Unassigned Synthetic Patient",
            date_of_birth="1991-02-03",
            sex=Patient.Sex.FEMALE,
            registered_by=self.receptionist,
        )
        self.client.force_login(self.doctor)
        response = self.client.get(reverse("patient_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.patient.full_name)
        self.assertNotContains(response, other_patient.full_name)

    def test_staff_registration_cannot_request_administrator_role(self):
        form = StaffRegistrationRequestForm(
            data={
                "first_name": "Synthetic",
                "last_name": "Applicant",
                "username": "syntheticapplicant",
                "email": "applicant@example.invalid",
                "role": User.Role.ADMIN,
                "department": "",
                "staff_id": "STF-TEST",
                "password": "StrongPass123",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("role", form.errors)

    def test_logout_requires_post(self):
        self.client.force_login(self.receptionist)
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)
        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)
