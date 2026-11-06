import random
from datetime import timedelta

from django.db import models
from django.conf import settings
from django.utils import timezone
from patients.models import Patient


class Appointment(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        PENDING = "PENDING", "Scheduled"
        CONFIRMED = "CONFIRMED", "Confirmed"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="appointments")
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        limit_choices_to={"role": "DOCTOR"}, related_name="appointments",
    )
    reason = models.CharField(max_length=255)
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_at"]

    @property
    def normalized_status(self):
        if self.status == Appointment.Status.PENDING:
            return Appointment.Status.SCHEDULED
        return self.status

    def __str__(self):
        return f"{self.patient.full_name} with {self.doctor} at {self.scheduled_at}"


class AppointmentAuditLog(models.Model):
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="audit_logs")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointment_audit_actions",
    )
    action = models.CharField(max_length=60)
    old_status = models.CharField(max_length=20, choices=Appointment.Status.choices, blank=True)
    new_status = models.CharField(max_length=20, choices=Appointment.Status.choices, blank=True)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.appointment_id}: {self.action}"


class QueueEntry(models.Model):
    class Status(models.TextChoices):
        WAITING = "WAITING", "Waiting"
        CALLED = "CALLED", "Called"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="queue_entries")
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="queue_entries",
    )
    assigned_doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="queue_assignments",
        limit_choices_to={"role": "DOCTOR"},
    )
    queue_number = models.CharField(max_length=30, unique=True)
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.WAITING)
    source = models.CharField(max_length=20, default="WALK_IN", choices=[("WALK_IN", "Walk-in"), ("APPOINTMENT", "Appointment")])
    notes = models.TextField(blank=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="queue_entries_added",
    )
    called_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["queue_number"]

    @staticmethod
    def generate_queue_number():
        prefix = f"Q{timezone.localdate().strftime('%d%m%y')}"
        existing = QueueEntry.objects.filter(queue_number__startswith=f"{prefix}-")
        last_suffix = 0
        for queue_number in existing.values_list("queue_number", flat=True):
            try:
                suffix = int(queue_number.rsplit("-", 1)[-1])
                if suffix > last_suffix:
                    last_suffix = suffix
            except (TypeError, ValueError):
                continue
        return f"{prefix}-{last_suffix + 1:03d}"

    def __str__(self):
        return f"{self.queue_number} - {self.patient.full_name}"


class QueueAuditLog(models.Model):
    queue_entry = models.ForeignKey(QueueEntry, on_delete=models.CASCADE, related_name="audit_logs")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="queue_audit_actions",
    )
    action = models.CharField(max_length=80)
    old_status = models.CharField(max_length=25, choices=QueueEntry.Status.choices, blank=True)
    new_status = models.CharField(max_length=25, choices=QueueEntry.Status.choices, blank=True)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.queue_entry.queue_number}: {self.action}"
