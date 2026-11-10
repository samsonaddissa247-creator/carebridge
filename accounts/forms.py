from django import forms
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import User


class StaffLoginForm(AuthenticationForm):
    username = forms.CharField(label="Staff ID or username", widget=forms.TextInput(attrs={"placeholder": "e.g. STF-2291"}))
    password = forms.CharField(label="Password", widget=forms.PasswordInput(attrs={"placeholder": "••••••••"}))


class StaffRegistrationRequestForm(forms.ModelForm):
    """A prospective staff member requests an account. It is created inactive
    and unapproved until a Hospital Administrator reviews and approves it —
    this is the verification gate described in the project proposal."""
    role = forms.ChoiceField(
        choices=[(role.value, role.label) for role in User.Role if role != User.Role.ADMIN],
    )
    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email", "role", "department", "staff_id", "password"]

    def clean_password(self):
        password = self.cleaned_data["password"]
        candidate = User(
            username=self.cleaned_data.get("username", ""),
            email=self.cleaned_data.get("email", ""),
            first_name=self.cleaned_data.get("first_name", ""),
            last_name=self.cleaned_data.get("last_name", ""),
        )
        try:
            validate_password(password, candidate)
        except DjangoValidationError as exc:
            raise forms.ValidationError(exc.messages) from exc
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        user.is_active = False
        user.is_approved = False
        if commit:
            user.save()
        return user
