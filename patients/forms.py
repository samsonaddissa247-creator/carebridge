from django import forms

from accounts.models import User
from .models import ConsultationRecord, MedicalHistory, Patient, VitalSigns


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = [
            "full_name", "date_of_birth", "sex", "phone_number",
            "next_of_kin", "allergies", "chronic_conditions", "notes",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "full_name": forms.TextInput(attrs={"placeholder": "e.g. Tendai Moyo"}),
            "phone_number": forms.TextInput(attrs={"placeholder": "+263 7X XXX XXXX"}),
            "next_of_kin": forms.TextInput(attrs={"placeholder": "Name and phone number"}),
            "allergies": forms.TextInput(attrs={"placeholder": "e.g. Penicillin"}),
            "chronic_conditions": forms.TextInput(attrs={"placeholder": "e.g. Hypertension, Diabetes"}),
        }


class MedicalHistoryForm(forms.ModelForm):
    class Meta:
        model = MedicalHistory
        fields = [
            "previous_conditions",
            "past_illnesses",
            "previous_operations",
            "known_allergies",
            "family_history",
            "other_information",
        ]
        widgets = {
            "previous_conditions": forms.Textarea(attrs={"rows": 3}),
            "past_illnesses": forms.Textarea(attrs={"rows": 3}),
            "previous_operations": forms.Textarea(attrs={"rows": 3}),
            "known_allergies": forms.Textarea(attrs={"rows": 2}),
            "family_history": forms.Textarea(attrs={"rows": 2}),
            "other_information": forms.Textarea(attrs={"rows": 3}),
        }


class ConsultationRecordForm(forms.ModelForm):
    class Meta:
        model = ConsultationRecord
        fields = [
            "doctor",
            "consultation_datetime",
            "presenting_complaint",
            "symptoms",
            "clinical_observations",
            "assessment",
            "notes",
            "follow_up_instructions",
        ]
        widgets = {
            "consultation_datetime": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "presenting_complaint": forms.Textarea(attrs={"rows": 3}),
            "symptoms": forms.Textarea(attrs={"rows": 3}),
            "clinical_observations": forms.Textarea(attrs={"rows": 3}),
            "assessment": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "follow_up_instructions": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["doctor"].queryset = User.objects.filter(role=User.Role.DOCTOR).order_by("last_name", "first_name")
        if user and user.role == User.Role.DOCTOR:
            self.fields["doctor"].initial = user
            self.fields["doctor"].queryset = User.objects.filter(pk=user.pk, role=User.Role.DOCTOR)

    def clean(self):
        cleaned_data = super().clean()
        doctor = cleaned_data.get("doctor")
        if doctor and doctor.role != User.Role.DOCTOR:
            raise forms.ValidationError("Only doctors may create consultation records.")
        return cleaned_data


class VitalSignsForm(forms.ModelForm):
    class Meta:
        model = VitalSigns
        fields = [
            "recorded_at",
            "blood_pressure",
            "temperature",
            "pulse_rate",
            "respiratory_rate",
            "oxygen_saturation",
            "weight_kg",
            "notes",
        ]
        widgets = {
            "recorded_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "blood_pressure": forms.TextInput(attrs={"placeholder": "e.g. 120/80 mmHg"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_blood_pressure(self):
        value = (self.cleaned_data.get("blood_pressure") or "").strip()
        if value and "/" not in value:
            raise forms.ValidationError("Blood pressure should use the format systolic/diastolic, for example 120/80 mmHg.")
        return value

    def clean_temperature(self):
        value = self.cleaned_data.get("temperature")
        if value is not None and not (30 <= float(value) <= 45):
            raise forms.ValidationError("Temperature should be recorded in degrees Celsius within a realistic clinical range.")
        return value

    def clean_pulse_rate(self):
        value = self.cleaned_data.get("pulse_rate")
        if value is not None and not (20 <= value <= 220):
            raise forms.ValidationError("Pulse rate should be between 20 and 220 bpm.")
        return value

    def clean_respiratory_rate(self):
        value = self.cleaned_data.get("respiratory_rate")
        if value is not None and not (4 <= value <= 80):
            raise forms.ValidationError("Respiratory rate should be between 4 and 80 breaths per minute.")
        return value

    def clean_oxygen_saturation(self):
        value = self.cleaned_data.get("oxygen_saturation")
        if value is not None and not (50 <= value <= 100):
            raise forms.ValidationError("Oxygen saturation should be between 50% and 100%.")
        return value

    def clean_weight_kg(self):
        value = self.cleaned_data.get("weight_kg")
        if value is not None and not (2 <= float(value) <= 300):
            raise forms.ValidationError("Weight should be between 2 kg and 300 kg.")
        return value
