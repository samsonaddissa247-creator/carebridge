from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from appointments.models import QueueEntry
from patients.models import ConsultationRecord, MedicalHistory, Patient, VitalSigns


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MedicalRecordsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="adminmed",
            password="StrongPass123!",
            first_name="Admin",
            last_name="User",
            email="adminmed@example.com",
            role=User.Role.ADMIN,
            is_approved=True,
            is_active=True,
        )
        self.receptionist = User.objects.create_user(
            username="receptionmed",
            password="StrongPass123!",
            first_name="Front",
            last_name="Desk",
            email="receptionmed@example.com",
            role=User.Role.RECEPTIONIST,
            is_approved=True,
            is_active=True,
        )
        self.doctor = User.objects.create_user(
            username="doctormed",
            password="StrongPass123!",
            first_name="Doctor",
            last_name="User",
            email="doctormed@example.com",
            role=User.Role.DOCTOR,
            is_approved=True,
            is_active=True,
        )
        self.patient = Patient.objects.create(
            full_name="Medical Patient",
            date_of_birth="1988-05-04",
            sex=Patient.Sex.FEMALE,
            phone_number="+263771234567",
            registered_by=self.receptionist,
        )
        QueueEntry.objects.create(
            patient=self.patient,
            assigned_doctor=self.doctor,
            queue_number="Q-MEDICAL-1",
        )

    def test_doctor_can_create_medical_history(self):
        self.client.login(username="doctormed", password="StrongPass123!")
        response = self.client.post(
            reverse("add_medical_history", args=[self.patient.pk]),
            {
                "previous_conditions": "Asthma",
                "past_illnesses": "Influenza in 2024",
                "previous_operations": "Appendectomy",
                "known_allergies": "Penicillin",
                "family_history": "Mother with hypertension",
                "other_information": "No other notes",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Medical history added.")
        self.assertTrue(MedicalHistory.objects.filter(patient=self.patient).exists())

    def test_doctor_can_create_consultation_record(self):
        self.client.login(username="doctormed", password="StrongPass123!")
        response = self.client.post(
            reverse("add_consultation", args=[self.patient.pk]),
            {
                "doctor": self.doctor.pk,
                "consultation_datetime": "2026-11-10T10:00",
                "presenting_complaint": "Persistent headache",
                "symptoms": "Mild dizziness",
                "clinical_observations": "Stable patient",
                "assessment": "Observation only",
                "notes": "Follow-up in two weeks",
                "follow_up_instructions": "Return if worsening",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Consultation record created.")
        self.assertTrue(ConsultationRecord.objects.filter(patient=self.patient).exists())

    def test_doctor_can_record_vital_signs(self):
        self.client.login(username="doctormed", password="StrongPass123!")
        response = self.client.post(
            reverse("add_vital_signs", args=[self.patient.pk]),
            {
                "recorded_at": "2026-11-10T09:30",
                "blood_pressure": "120/80",
                "temperature": "36.8",
                "pulse_rate": "72",
                "respiratory_rate": "18",
                "oxygen_saturation": "98",
                "weight_kg": "65.0",
                "notes": "Vitals within range",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vital signs recorded.")
        self.assertTrue(VitalSigns.objects.filter(patient=self.patient).exists())

    def test_receptionist_cannot_access_private_clinical_records(self):
        self.client.login(username="receptionmed", password="StrongPass123!")
        response = self.client.get(reverse("medical_record_history", args=[self.patient.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertIn(b"restricted", response.content)

    def test_doctor_can_view_patient_medical_records(self):
        self.client.login(username="doctormed", password="StrongPass123!")
        response = self.client.get(reverse("medical_record_history", args=[self.patient.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.patient.full_name)

    def test_invalid_form_submission_is_rejected(self):
        self.client.login(username="doctormed", password="StrongPass123!")
        response = self.client.post(
            reverse("add_consultation", args=[self.patient.pk]),
            {"doctor": self.doctor.pk, "presenting_complaint": ""},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required")

    def test_record_correction_is_logged(self):
        self.client.login(username="doctormed", password="StrongPass123!")
        response = self.client.post(
            reverse("correct_record", args=[self.patient.pk]),
            {"details": "Corrected follow-up note"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Medical record correction noted")

    def test_doctor_cannot_access_unassigned_patient_records(self):
        other_patient = Patient.objects.create(
            full_name="Unassigned Synthetic Patient",
            date_of_birth="1991-02-03",
            sex=Patient.Sex.MALE,
            registered_by=self.receptionist,
        )
        self.client.force_login(self.doctor)
        response = self.client.get(reverse("medical_record_history", args=[other_patient.pk]))
        self.assertEqual(response.status_code, 404)
        response = self.client.post(
            reverse("add_consultation", args=[other_patient.pk]),
            {
                "doctor": self.doctor.pk,
                "consultation_datetime": "2026-11-10T10:00",
                "presenting_complaint": "Synthetic test",
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_receptionist_cannot_change_clinical_fields_with_tampered_form(self):
        self.client.force_login(self.receptionist)
        response = self.client.post(
            reverse("update_patient", args=[self.patient.pk]),
            {
                "full_name": self.patient.full_name,
                "date_of_birth": "1988-05-04",
                "sex": Patient.Sex.FEMALE,
                "phone_number": "000",
                "allergies": "Tampered allergy",
                "chronic_conditions": "Tampered condition",
                "notes": "Tampered note",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.allergies, "")
        self.assertEqual(self.patient.chronic_conditions, "")
        self.assertEqual(self.patient.notes, "")
