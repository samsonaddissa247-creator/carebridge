from django import forms
from .models import Patient


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
