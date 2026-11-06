import uuid

from django.conf import settings
from django.db import models


def generate_patient_id():
    return "CB-" + uuid.uuid4().hex[:6].upper()


class Patient(models.Model):
    class Sex(models.TextChoices):
        FEMALE = "F", "Female"
        MALE = "M", "Male"

    patient_id = models.CharField(max_length=12, unique=True, default=generate_patient_id, editable=False)
    full_name = models.CharField(max_length=150)
    date_of_birth = models.DateField()
    sex = models.CharField(max_length=1, choices=Sex.choices)
    phone_number = models.CharField(max_length=20, blank=True)
    next_of_kin = models.CharField(max_length=150, blank=True, help_text="Name and phone number")
    allergies = models.CharField(max_length=255, blank=True)
    chronic_conditions = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    registered_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="patients_registered"
    )

    class Meta:
        ordering = ["-registered_at"]

    def __str__(self):
        return f"{self.full_name} ({self.patient_id})"


class MedicalHistory(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="medical_histories")
    previous_conditions = models.TextField(blank=True)
    past_illnesses = models.TextField(blank=True)
    previous_operations = models.TextField(blank=True)
    known_allergies = models.TextField(blank=True)
    family_history = models.TextField(blank=True)
    other_information = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="medical_histories_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Medical history for {self.patient.full_name}"


class ConsultationRecord(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="consultations")
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consultations_done",
        limit_choices_to={"role": "DOCTOR"},
    )
    consultation_datetime = models.DateTimeField()
    presenting_complaint = models.TextField()
    symptoms = models.TextField(blank=True)
    clinical_observations = models.TextField(blank=True)
    assessment = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    follow_up_instructions = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consultations_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-consultation_datetime"]

    def __str__(self):
        return f"Consultation for {self.patient.full_name} on {self.consultation_datetime}"


class VitalSigns(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="vital_signs")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vital_signs_recorded",
    )
    recorded_at = models.DateTimeField()
    blood_pressure = models.CharField(max_length=20, blank=True)
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    pulse_rate = models.IntegerField(null=True, blank=True)
    respiratory_rate = models.IntegerField(null=True, blank=True)
    oxygen_saturation = models.IntegerField(null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"Vital signs for {self.patient.full_name} ({self.recorded_at})"


class MedicalRecordAuditLog(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="medical_record_audit_logs")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="medical_record_actions",
    )
    action = models.CharField(max_length=80)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.patient.full_name}: {self.action}"
