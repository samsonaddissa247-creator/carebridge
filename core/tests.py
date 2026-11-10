from datetime import datetime, time, timedelta
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from appointments.models import (
    Appointment,
    AppointmentAuditLog,
    QueueEntry,
)
from assistant.operational import build_operational_summary
from billing.models import Invoice
from laboratory.models import LabRequest, LabResult
from patients.models import ConsultationRecord, MedicalHistory, Patient


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DashboardAndReportsTests(TestCase):
    def setUp(self):
        self.admin = self.make_user("reportadmin", User.Role.ADMIN)
        self.receptionist = self.make_user("reportreception", User.Role.RECEPTIONIST)
        self.doctor = self.make_user("reportdoctor", User.Role.DOCTOR)
        self.other_doctor = self.make_user("otherreportdoctor", User.Role.DOCTOR)
        self.lab_technician = self.make_user("reportlabtech", User.Role.LAB_TECHNICIAN)
        self.today = timezone.localdate()
        self.patient = self.make_patient("Synthetic Report Patient")
        self.other_patient = self.make_patient("Other Synthetic Report Patient")

    def make_user(self, username, role):
        return User.objects.create_user(
            username=username,
            password="StrongPass123",
            role=role,
            is_approved=True,
            is_active=True,
        )

    def make_patient(self, name):
        return Patient.objects.create(
            full_name=name,
            date_of_birth="1990-01-02",
            sex=Patient.Sex.FEMALE,
            phone_number="+263771234567",
            registered_by=self.receptionist if hasattr(self, "receptionist") else None,
        )

    def make_appointment(self, patient, doctor, offset_days=0, status=Appointment.Status.SCHEDULED):
        scheduled_date = self.today + timedelta(days=offset_days)
        scheduled_at = timezone.make_aware(datetime.combine(scheduled_date, time(10, 0)))
        return Appointment.objects.create(
            patient=patient,
            doctor=doctor,
            reason="Synthetic appointment",
            scheduled_at=scheduled_at,
            status=status,
        )

    def make_queue_entry(self, patient, doctor, status, queue_number):
        return QueueEntry.objects.create(
            patient=patient,
            assigned_doctor=doctor,
            queue_number=queue_number,
            status=status,
        )

    def test_admin_dashboard_aggregates_operations_and_activity_without_patient_details(self):
        self.make_appointment(self.patient, self.doctor, status=Appointment.Status.SCHEDULED)
        self.make_appointment(self.patient, self.doctor, status=Appointment.Status.COMPLETED)
        self.make_appointment(self.patient, self.doctor, status=Appointment.Status.CANCELLED)
        self.make_queue_entry(self.patient, self.doctor, QueueEntry.Status.WAITING, "Q-ADMIN-1")
        self.make_queue_entry(self.patient, self.doctor, QueueEntry.Status.IN_PROGRESS, "Q-ADMIN-2")
        LabRequest.objects.create(patient=self.patient, requested_by=self.doctor, test_name="Synthetic panel")
        AppointmentAuditLog.objects.create(
            appointment=Appointment.objects.first(),
            actor=self.receptionist,
            action="created",
            details=f"Patient {self.patient.full_name}",
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["patients_total"], 2)
        self.assertEqual(response.context["appointments_today"], 2)
        self.assertEqual(response.context["completed_appointments_today"], 1)
        self.assertEqual(response.context["cancelled_appointments_today"], 1)
        self.assertEqual(response.context["patients_waiting"], 1)
        self.assertEqual(response.context["patients_in_progress"], 1)
        self.assertEqual(response.context["pending_lab_requests"], 1)
        self.assertContains(response, "Recent system activity")
        self.assertNotContains(response, "Patient Synthetic Report Patient")
        self.assertNotIn(
            self.patient.full_name,
            str(response.context["recent_activities"]),
        )

    def test_reception_dashboard_shows_front_desk_work_without_clinical_data(self):
        self.make_appointment(self.patient, self.doctor, status=Appointment.Status.CONFIRMED)
        self.make_appointment(self.other_patient, self.doctor, offset_days=1)
        self.make_queue_entry(self.patient, self.doctor, QueueEntry.Status.WAITING, "Q-RECP-1")
        self.make_queue_entry(self.other_patient, self.doctor, QueueEntry.Status.COMPLETED, "Q-RECP-2")
        MedicalHistory.objects.create(patient=self.patient, known_allergies="PRIVATE-SYNTHETIC-ALLERGY")
        lab_request = LabRequest.objects.create(
            patient=self.patient,
            requested_by=self.doctor,
            test_name="PRIVATE-SYNTHETIC-TEST",
            status=LabRequest.Status.COMPLETED,
        )
        LabResult.objects.create(lab_request=lab_request, result_value="PRIVATE-SYNTHETIC-RESULT")
        self.client.force_login(self.receptionist)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["registered_today"], 2)
        self.assertEqual(response.context["appointments_today_count"], 1)
        self.assertEqual(response.context["waiting_count"], 1)
        self.assertEqual(response.context["completed_queue_count"], 1)
        self.assertContains(response, self.patient.full_name)
        self.assertNotContains(response, "PRIVATE-SYNTHETIC-ALLERGY")
        self.assertNotContains(response, "PRIVATE-SYNTHETIC-RESULT")
        self.assertNotContains(response, "PRIVATE-SYNTHETIC-TEST")

    def test_doctor_dashboard_is_scoped_to_own_assignments_and_unverified_results(self):
        own_appointment = self.make_appointment(self.patient, self.doctor)
        self.make_appointment(self.other_patient, self.other_doctor)
        self.make_queue_entry(self.patient, self.doctor, QueueEntry.Status.WAITING, "Q-DOC-1")
        self.make_queue_entry(self.other_patient, self.other_doctor, QueueEntry.Status.WAITING, "Q-DOC-2")
        ConsultationRecord.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            consultation_datetime=timezone.now(),
            presenting_complaint="Synthetic complaint",
        )
        lab_request = LabRequest.objects.create(
            patient=self.patient,
            requested_by=self.doctor,
            test_name="Synthetic result request",
            status=LabRequest.Status.COMPLETED,
        )
        LabResult.objects.create(lab_request=lab_request, result_value="Synthetic result")
        self.client.force_login(self.doctor)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["today_count"], 1)
        self.assertEqual(response.context["waiting_count"], 1)
        self.assertEqual(response.context["completed_consultations_today"], 1)
        self.assertEqual(response.context["pending_lab_review"], 1)
        self.assertContains(response, self.patient.full_name)
        self.assertNotContains(response, self.other_patient.full_name)
        self.assertEqual(response.context["appointments_today"].get(), own_appointment)

    def test_lab_technician_dashboard_includes_unverified_results(self):
        pending = LabRequest.objects.create(
            patient=self.patient,
            requested_by=self.doctor,
            test_name="Synthetic unverified",
            status=LabRequest.Status.COMPLETED,
        )
        LabResult.objects.create(lab_request=pending, result_value="Synthetic result")
        LabRequest.objects.create(
            patient=self.other_patient,
            requested_by=self.doctor,
            test_name="Synthetic processing",
            status=LabRequest.Status.PROCESSING,
        )
        self.client.force_login(self.lab_technician)
        dashboard_response = self.client.get(reverse("dashboard"))
        self.assertRedirects(dashboard_response, reverse("lab_dashboard"))
        response = self.client.get(reverse("lab_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["status_counts"][LabRequest.Status.PROCESSING], 1)
        self.assertEqual(response.context["awaiting_verification_count"], 1)

    def test_report_date_filter_calculates_daily_weekly_monthly_and_queue_data(self):
        self.make_appointment(self.patient, self.doctor, status=Appointment.Status.COMPLETED)
        self.make_appointment(self.patient, self.other_doctor, offset_days=1)
        self.make_appointment(self.other_patient, self.doctor, offset_days=-2)
        ConsultationRecord.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            consultation_datetime=timezone.make_aware(datetime.combine(self.today, time(11, 0))),
            presenting_complaint="Synthetic report consultation",
        )
        self.make_queue_entry(self.patient, self.doctor, QueueEntry.Status.COMPLETED, "Q-REPORT-1")
        self.make_queue_entry(self.other_patient, self.doctor, QueueEntry.Status.CANCELLED, "Q-REPORT-2")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reports"), {"date": self.today.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["daily_appointments_total"], 1)
        self.assertEqual(response.context["weekly_appointments_total"], 2)
        self.assertEqual(response.context["monthly_appointments_total"], 3)
        self.assertEqual(response.context["queue_total"], 2)
        self.assertEqual(response.context["queue_completed"], 1)
        self.assertEqual(response.context["queue_cancelled"], 1)
        self.assertEqual(response.context["queue_completion_percent"], 100)
        self.assertEqual(response.context["patient_registrations"], 2)
        self.client.force_login(self.doctor)
        doctor_response = self.client.get(reverse("reports"), {"date": self.today.isoformat()})
        self.assertEqual(doctor_response.context["daily_appointments_total"], 1)
        self.assertEqual(doctor_response.context["weekly_appointments_total"], 1)
        self.assertEqual(doctor_response.context["monthly_appointments_total"], 2)
        self.assertEqual(doctor_response.context["consultations_on_date"], 1)
        self.assertEqual(doctor_response.context["consultations_this_week"], 1)
        self.assertEqual(doctor_response.context["consultations_this_month"], 1)

    def test_reports_are_role_scoped_and_do_not_show_result_values(self):
        self.make_appointment(self.patient, self.doctor)
        lab_request = LabRequest.objects.create(
            patient=self.patient,
            requested_by=self.doctor,
            test_name="PRIVATE-REPORT-TEST",
            status=LabRequest.Status.COMPLETED,
        )
        LabResult.objects.create(lab_request=lab_request, result_value="PRIVATE-REPORT-RESULT")
        self.client.force_login(self.receptionist)
        receptionist_response = self.client.get(reverse("reports"), {"date": self.today.isoformat()})
        self.assertEqual(receptionist_response.status_code, 200)
        self.assertFalse(receptionist_response.context["can_view_lab_reports"])
        self.assertNotContains(receptionist_response, "PRIVATE-REPORT-RESULT")
        self.assertNotContains(receptionist_response, "PRIVATE-REPORT-TEST")

        self.client.force_login(self.lab_technician)
        lab_response = self.client.get(reverse("reports"), {"date": self.today.isoformat()})
        self.assertEqual(lab_response.status_code, 200)
        self.assertTrue(lab_response.context["can_view_lab_reports"])
        self.assertNotContains(lab_response, "Appointments by status")
        self.assertNotContains(lab_response, "PRIVATE-REPORT-RESULT")

    def test_invalid_report_date_is_rejected(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reports"), {"date": "not-a-date"})
        self.assertEqual(response.status_code, 400)

    def test_unrecognised_role_cannot_access_dashboard_or_reports(self):
        unknown = self.make_user("unknownreportrole", "UNKNOWN")
        self.client.force_login(unknown)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("reports")).status_code, 403)

    def test_reports_handle_empty_data(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reports"), {"date": self.today.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["daily_appointments_total"], 0)
        self.assertEqual(response.context["weekly_appointments_total"], 0)
        self.assertEqual(response.context["monthly_appointments_total"], 0)
        self.assertEqual(response.context["queue_completion_percent"], 0)

    def test_ai_summary_matches_reported_role_scoped_counts(self):
        self.make_appointment(self.patient, self.doctor, status=Appointment.Status.COMPLETED)
        self.make_queue_entry(self.patient, self.doctor, QueueEntry.Status.IN_PROGRESS, "Q-AI-1")
        lab_request = LabRequest.objects.create(
            patient=self.patient,
            requested_by=self.doctor,
            test_name="Synthetic AI summary test",
            status=LabRequest.Status.COMPLETED,
        )
        LabResult.objects.create(lab_request=lab_request, result_value="Sensitive result not sent")
        doctor_summary = build_operational_summary(self.doctor)
        self.assertEqual(doctor_summary["my_appointments_completed_today"], 1)
        self.assertEqual(doctor_summary["my_patients_in_progress_today"], 1)
        self.assertEqual(
            LabRequest.objects.filter(
                requested_by=self.doctor,
                status=LabRequest.Status.COMPLETED,
                result__verified_at__isnull=True,
            ).count(),
            1,
        )
        self.assertNotIn("Sensitive result not sent", str(doctor_summary))
        admin_summary = build_operational_summary(self.admin)
        self.assertEqual(admin_summary["appointments_completed_today"], 1)
        receptionist_summary = build_operational_summary(self.receptionist)
        self.assertEqual(receptionist_summary["patients_in_progress_today"], 1)
        self.assertEqual(receptionist_summary["patients_registered_today"], 2)
        self.assertEqual(build_operational_summary(self.doctor)["my_lab_results_awaiting_review"], 1)

    def test_patient_names_and_clinical_audit_details_are_not_in_admin_activity(self):
        appointment = self.make_appointment(self.patient, self.doctor)
        AppointmentAuditLog.objects.create(
            appointment=appointment,
            actor=self.receptionist,
            action="status_update",
            details=f"Sensitive patient detail: {self.patient.full_name}",
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Appointment status updated")
        self.assertNotIn(
            self.patient.full_name,
            str(response.context["recent_activities"]),
        )
        self.assertNotContains(response, "Sensitive patient detail")
