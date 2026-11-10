from django import forms

from accounts.models import User
from patients.models import ConsultationRecord

from .models import LabRequest, LabResult
from .permissions import doctor_patient_queryset


class LabRequestForm(forms.ModelForm):
    class Meta:
        model = LabRequest
        fields = ["patient", "consultation", "test_name", "clinical_notes", "priority"]
        widgets = {
            "clinical_notes": forms.Textarea(attrs={"rows": 3}),
            "test_name": forms.TextInput(attrs={"placeholder": "e.g. Full blood count"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = doctor_patient_queryset(user).order_by("full_name")
        self.fields["consultation"].queryset = ConsultationRecord.objects.filter(
            doctor=user,
            patient__in=doctor_patient_queryset(user),
        ).select_related("patient").order_by("-consultation_datetime")

    def clean(self):
        cleaned_data = super().clean()
        patient = cleaned_data.get("patient")
        consultation = cleaned_data.get("consultation")
        if consultation and patient and consultation.patient_id != patient.pk:
            self.add_error("consultation", "Choose a consultation belonging to the selected patient.")
        return cleaned_data


class LabResultForm(forms.ModelForm):
    class Meta:
        model = LabResult
        fields = ["result_value", "units", "reference_range", "result_notes"]
        widgets = {
            "result_value": forms.Textarea(attrs={"rows": 4}),
            "result_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_result_value(self):
        value = (self.cleaned_data.get("result_value") or "").strip()
        if not value:
            raise forms.ValidationError("Enter the laboratory result.")
        return value
