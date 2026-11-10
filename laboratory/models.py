from django.conf import settings
from django.db import models

from patients.models import ConsultationRecord, Patient


class LabRequest(models.Model):
    class Priority(models.TextChoices):
        ROUTINE = "ROUTINE", "Routine"
        URGENT = "URGENT", "Urgent"
        STAT = "STAT", "STAT"

    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "Requested"
        COLLECTED = "COLLECTED", "Collected"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="lab_requests")
    consultation = models.ForeignKey(
        ConsultationRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="lab_requests_created",
        limit_choices_to={"role": "DOCTOR"},
    )
    test_name = models.CharField(max_length=150)
    clinical_notes = models.TextField(blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.ROUTINE)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="lab_req_status_created_idx"),
            models.Index(fields=["patient", "created_at"], name="lab_req_patient_created_idx"),
        ]

    def __str__(self):
        return f"{self.test_name} for {self.patient.patient_id}"


class LabResult(models.Model):
    lab_request = models.OneToOneField(LabRequest, on_delete=models.CASCADE, related_name="result")
    result_value = models.TextField()
    units = models.CharField(max_length=60, blank=True)
    reference_range = models.CharField(max_length=100, blank=True)
    result_notes = models.TextField(blank=True)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="lab_results_entered",
    )
    entered_at = models.DateTimeField(auto_now=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_results_verified",
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Result for {self.lab_request}"


class LabAuditLog(models.Model):
    lab_request = models.ForeignKey(LabRequest, on_delete=models.CASCADE, related_name="audit_logs")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_audit_actions",
    )
    action = models.CharField(max_length=40)
    old_status = models.CharField(max_length=12, choices=LabRequest.Status.choices, blank=True)
    new_status = models.CharField(max_length=12, choices=LabRequest.Status.choices, blank=True)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.lab_request}: {self.action}"
