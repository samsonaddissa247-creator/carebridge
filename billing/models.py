from django.db import models
from patients.models import Patient


class Invoice(models.Model):
    class Status(models.TextChoices):
        UNPAID = "UNPAID", "Unpaid"
        PAID = "PAID", "Paid"

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="invoices")
    description = models.CharField(max_length=255, help_text="e.g. Consultation, Lab test, Ward fee")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UNPAID)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invoice #{self.id} - {self.patient.full_name} - ${self.amount}"
