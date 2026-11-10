from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from laboratory.models import LabAuditLog, LabRequest, LabResult
from patients.models import ConsultationRecord, Patient


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LaboratoryWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="labadmin",
            password="StrongPass123",
            role=User.Role.ADMIN,
            is_approved=True,
        )
        self.doctor = User.objects.create_user(
            username="labdoctor",
            password="StrongPass123",
            role=User.Role.DOCTOR,
            is_approved=True,
        )
        self.other_doctor = User.objects.create_user(
            username="otherdoctor",
            password="StrongPass123",
            role=User.Role.DOCTOR,
            is_approved=True,
        )
        self.receptionist = User.objects.create_user(
            username="labreception",
            password="StrongPass123",
            role=User.Role.RECEPTIONIST,
            is_approved=True,
        )
        self.technician = User.objects.create_user(
            username="labtech",
            password="StrongPass123",
            role=User.Role.LAB_TECHNICIAN,
            is_approved=True,
        )
        self.patient = Patient.objects.create(
            full_name="Synthetic Lab Patient",
            date_of_birth="1990-02-03",
            sex=Patient.Sex.FEMALE,
            registered_by=self.receptionist,
        )
        self.consultation = ConsultationRecord.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            created_by=self.doctor,
            consultation_datetime="2026-11-10T08:00:00Z",
            presenting_complaint="Synthetic test complaint",
        )

    def make_request(self):
        return LabRequest.objects.create(
            patient=self.patient,
            consultation=self.consultation,
            requested_by=self.doctor,
            test_name="Full blood count",
        )

    def test_doctor_can_create_request_and_creation_is_audited(self):
        self.client.login(username="labdoctor", password="StrongPass123")
        response = self.client.post(
            reverse("lab_create_request"),
            {
                "patient": self.patient.pk,
                "consultation": self.consultation.pk,
                "test_name": "Full blood count",
                "clinical_notes": "Synthetic test notes",
                "priority": LabRequest.Priority.ROUTINE,
            },
        )
        lab_request = LabRequest.objects.get(test_name="Full blood count")
        self.assertRedirects(response, reverse("lab_detail", args=[lab_request.pk]))
        self.assertEqual(lab_request.requested_by, self.doctor)
        self.assertTrue(LabAuditLog.objects.filter(lab_request=lab_request, action="request_created").exists())

    def test_doctor_cannot_request_for_patient_without_access(self):
        patient = Patient.objects.create(
            full_name="Unauthorised Synthetic Patient",
            date_of_birth="1985-06-07",
            sex=Patient.Sex.MALE,
            registered_by=self.receptionist,
        )
        self.client.login(username="labdoctor", password="StrongPass123")
        response = self.client.post(
            reverse("lab_create_request"),
            {
                "patient": patient.pk,
                "test_name": "Glucose",
                "priority": LabRequest.Priority.ROUTINE,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(LabRequest.objects.filter(patient=patient).exists())

    def test_valid_status_progression_and_invalid_transition(self):
        lab_request = self.make_request()
        self.client.login(username="labtech", password="StrongPass123")
        invalid_response = self.client.post(
            reverse("lab_update_status", args=[lab_request.pk]),
            {"status": LabRequest.Status.PROCESSING},
            follow=True,
        )
        lab_request.refresh_from_db()
        self.assertEqual(lab_request.status, LabRequest.Status.REQUESTED)
        self.assertContains(invalid_response, "not allowed", status_code=200)

        response = self.client.post(
            reverse("lab_update_status", args=[lab_request.pk]),
            {"status": LabRequest.Status.COLLECTED},
        )
        self.assertRedirects(response, reverse("lab_detail", args=[lab_request.pk]))
        lab_request.refresh_from_db()
        self.assertEqual(lab_request.status, LabRequest.Status.COLLECTED)
        self.assertTrue(
            LabAuditLog.objects.filter(
                lab_request=lab_request,
                action="status_changed",
                old_status=LabRequest.Status.REQUESTED,
                new_status=LabRequest.Status.COLLECTED,
                actor=self.technician,
            ).exists()
        )

    def test_result_entry_completion_and_verification_are_audited(self):
        lab_request = self.make_request()
        lab_request.status = LabRequest.Status.PROCESSING
        lab_request.save(update_fields=["status"])
        self.client.login(username="labtech", password="StrongPass123")
        response = self.client.post(
            reverse("lab_save_result", args=[lab_request.pk]),
            {
                "result_value": "Synthetic result: within reference range",
                "units": "g/L",
                "reference_range": "Synthetic range",
                "result_notes": "No interpretation generated.",
            },
        )
        self.assertRedirects(response, reverse("lab_detail", args=[lab_request.pk]))
        result = LabResult.objects.get(lab_request=lab_request)
        self.assertEqual(result.entered_by, self.technician)
        self.assertIsNotNone(result.entered_at)
        self.assertTrue(
            LabAuditLog.objects.filter(lab_request=lab_request, action="result_entered", actor=self.technician).exists()
        )

        response = self.client.post(
            reverse("lab_update_status", args=[lab_request.pk]),
            {"status": LabRequest.Status.COMPLETED},
        )
        self.assertRedirects(response, reverse("lab_detail", args=[lab_request.pk]))
        self.client.post(reverse("lab_verify_result", args=[lab_request.pk]))
        result.refresh_from_db()
        self.assertEqual(result.verified_by, self.technician)
        self.assertIsNotNone(result.verified_at)
        self.assertTrue(
            LabAuditLog.objects.filter(lab_request=lab_request, action="result_verified", actor=self.technician).exists()
        )
        self.client.post(
            reverse("lab_save_result", args=[lab_request.pk]),
            {
                "result_value": "Corrected synthetic result",
                "units": "g/L",
                "reference_range": "Synthetic range",
                "result_notes": "Correction recorded.",
            },
        )
        result.refresh_from_db()
        self.assertEqual(result.result_value, "Corrected synthetic result")
        self.assertIsNone(result.verified_at)
        self.assertTrue(
            LabAuditLog.objects.filter(
                lab_request=lab_request,
                action="result_corrected",
                actor=self.technician,
            ).exists()
        )

    def test_completion_requires_a_result(self):
        lab_request = self.make_request()
        lab_request.status = LabRequest.Status.PROCESSING
        lab_request.save(update_fields=["status"])
        self.client.login(username="labtech", password="StrongPass123")
        response = self.client.post(
            reverse("lab_update_status", args=[lab_request.pk]),
            {"status": LabRequest.Status.COMPLETED},
            follow=True,
        )
        lab_request.refresh_from_db()
        self.assertEqual(lab_request.status, LabRequest.Status.PROCESSING)
        self.assertContains(response, "Enter a result")

    def test_doctor_can_review_own_request_but_not_another_doctors_patient(self):
        own_request = self.make_request()
        LabResult.objects.create(
            lab_request=own_request,
            result_value="Unverified synthetic result",
            entered_by=self.technician,
        )
        other_patient = Patient.objects.create(
            full_name="Other Synthetic Patient",
            date_of_birth="1991-04-05",
            sex=Patient.Sex.MALE,
            registered_by=self.receptionist,
        )
        other_request = LabRequest.objects.create(
            patient=other_patient,
            requested_by=self.other_doctor,
            test_name="Synthetic panel",
        )
        self.client.login(username="labdoctor", password="StrongPass123")
        own_response = self.client.get(reverse("lab_detail", args=[own_request.pk]))
        self.assertEqual(own_response.status_code, 200)
        self.assertContains(own_response, "Not verified")
        self.assertEqual(self.client.get(reverse("lab_detail", args=[other_request.pk])).status_code, 404)

    def test_receptionist_is_denied_access_and_doctor_cannot_manage_status(self):
        lab_request = self.make_request()
        self.client.login(username="labreception", password="StrongPass123")
        self.assertEqual(self.client.get(reverse("lab_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("lab_detail", args=[lab_request.pk])).status_code, 403)

        self.client.login(username="labdoctor", password="StrongPass123")
        response = self.client.post(
            reverse("lab_update_status", args=[lab_request.pk]),
            {"status": LabRequest.Status.COLLECTED},
        )
        self.assertEqual(response.status_code, 403)
        lab_request.refresh_from_db()
        self.assertEqual(lab_request.status, LabRequest.Status.REQUESTED)

    def test_lab_technician_can_access_dashboard(self):
        self.client.login(username="labtech", password="StrongPass123")
        response = self.client.get(reverse("lab_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Laboratory")
        self.assertEqual(self.client.get(reverse("reports")).status_code, 403)
