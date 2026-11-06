from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from accounts.models import User
from patients.models import Patient
from .models import Appointment, QueueEntry


class AppointmentForm(forms.ModelForm):
    cancel_reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Reason for cancellation"}))

    class Meta:
        model = Appointment
        fields = ["patient", "doctor", "reason", "scheduled_at", "status", "notes"]
        widgets = {
            "scheduled_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "reason": forms.TextInput(attrs={"placeholder": "e.g. Follow-up consultation"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_scheduled_at(self):
        scheduled_at = self.cleaned_data.get("scheduled_at")
        if scheduled_at is None:
            raise ValidationError("Please provide a valid date and time.")
        if scheduled_at <= timezone.now():
            raise ValidationError("Appointment time must be in the future.")
        return scheduled_at

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status")
        cancel_reason = cleaned_data.get("cancel_reason") or ""

        if status == Appointment.Status.CANCELLED and not cancel_reason.strip():
            raise ValidationError({"cancel_reason": "A cancellation reason is required when cancelling an appointment."})

        if status != Appointment.Status.CANCELLED and cancel_reason.strip():
            cleaned_data["notes"] = (cleaned_data.get("notes") or "") + ("\nCancellation reason: " + cancel_reason.strip())

        if status == Appointment.Status.CANCELLED:
            cleaned_data["reason"] = cleaned_data.get("reason") or "Cancelled"

        return cleaned_data

    def save(self, commit=True):
        appointment = super().save(commit=False)
        if self.cleaned_data.get("status") == Appointment.Status.CANCELLED:
            appointment.reason = self.cleaned_data.get("reason") or "Cancelled"
            appointment.notes = (appointment.notes or "") + ("\nCancellation reason: " + self.cleaned_data.get("cancel_reason", "").strip())
        if commit:
            appointment.save()
        return appointment


class QueueEntryForm(forms.ModelForm):
    class Meta:
        model = QueueEntry
        fields = ["patient", "appointment", "assigned_doctor", "source", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
            "source": forms.Select(attrs={"class": "select"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = Patient.objects.all().order_by("full_name")
        self.fields["appointment"].queryset = Appointment.objects.select_related("patient", "doctor").order_by("scheduled_at")
        self.fields["assigned_doctor"].queryset = User.objects.filter(role=User.Role.DOCTOR).order_by("last_name", "first_name")
        self.fields["assigned_doctor"].required = False
        self.fields["appointment"].required = False
        if user and user.role == User.Role.DOCTOR:
            self.fields["assigned_doctor"].initial = user
            self.fields["assigned_doctor"].queryset = User.objects.filter(pk=user.pk, role=User.Role.DOCTOR)

    def clean(self):
        cleaned_data = super().clean()
        patient = cleaned_data.get("patient")
        appointment = cleaned_data.get("appointment")
        if appointment and patient and appointment.patient_id != patient.pk:
            raise ValidationError("Selected appointment does not belong to the selected patient.")
        if patient:
            active = QueueEntry.objects.filter(patient=patient).filter(
                status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.CALLED, QueueEntry.Status.IN_PROGRESS]
            )
            if appointment:
                active = active.filter(appointment=appointment)
            if active.exists():
                raise ValidationError("This patient already has an active queue entry for this visit.")
        return cleaned_data

    def save(self, commit=True):
        queue_entry = super().save(commit=False)
        if queue_entry.appointment and not queue_entry.assigned_doctor:
            queue_entry.assigned_doctor = queue_entry.appointment.doctor
        if queue_entry.appointment and queue_entry.source == "WALK_IN":
            queue_entry.source = "APPOINTMENT"
        if queue_entry.appointment and not queue_entry.assigned_doctor:
            queue_entry.assigned_doctor = queue_entry.appointment.doctor
        if commit:
            queue_entry.save()
        return queue_entry
