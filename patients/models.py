from django.db import models
import uuid


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
