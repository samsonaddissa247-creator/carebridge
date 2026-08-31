from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import User


class StaffLoginForm(AuthenticationForm):
    username = forms.CharField(label="Staff ID or username", widget=forms.TextInput(attrs={"placeholder": "e.g. STF-2291"}))
    password = forms.CharField(label="Password", widget=forms.PasswordInput(attrs={"placeholder": "••••••••"}))


class StaffRegistrationRequestForm(forms.ModelForm):
    """A prospective staff member requests an account. It is created inactive
    and unapproved until a Hospital Administrator reviews and approves it —
    this is the verification gate described in the project proposal."""
    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email", "role", "department", "staff_id", "password"]
        widgets = {
            "role": forms.Select(choices=[(r.value, r.label) for r in User.Role if r.value != "ADMIN"]),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        user.is_active = False
        user.is_approved = False
        if commit:
            user.save()
        return user
