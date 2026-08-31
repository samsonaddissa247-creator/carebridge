from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Hospital Administrator"
        DOCTOR = "DOCTOR", "Doctor"
        RECEPTIONIST = "RECEPTIONIST", "Receptionist"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.RECEPTIONIST)
    staff_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    department = models.CharField(max_length=100, blank=True)
    is_approved = models.BooleanField(
        default=False,
        help_text="Staff accounts must be approved by a Hospital Administrator before they can log in.",
    )

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"
