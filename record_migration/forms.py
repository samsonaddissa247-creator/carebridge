from pathlib import PurePath

from django import forms
from PIL import Image, UnidentifiedImageError

from patients.models import Patient

from .models import MigrationBatch
from .permissions import accessible_patients
from .services import ALLOWED_SPREADSHEET_EXTENSIONS, MAPPABLE_PATIENT_FIELDS, MAX_SPREADSHEET_SIZE, detect_spreadsheet

MAX_DOCUMENT_SIZE = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


class MigrationBatchForm(forms.ModelForm):
    class Meta:
        model = MigrationBatch
        fields = [
            "name",
            "migration_type",
            "source_hospital",
            "source_department",
            "source_system",
            "description",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class MigrationDocumentForm(forms.Form):
    patient = forms.ModelChoiceField(queryset=Patient.objects.none())
    file = forms.FileField()
    document_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    source = forms.CharField(max_length=150)
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = accessible_patients(user).order_by("full_name")

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        extension = PurePath(uploaded.name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError("Upload a PDF, JPG, JPEG, or PNG document.")
        if uploaded.size > MAX_DOCUMENT_SIZE:
            raise forms.ValidationError("Files must be 10 MB or smaller.")

        content = uploaded.read(MAX_DOCUMENT_SIZE + 1)
        uploaded.seek(0)
        if len(content) > MAX_DOCUMENT_SIZE:
            raise forms.ValidationError("Files must be 10 MB or smaller.")

        if extension == ".pdf":
            if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-1024:]:
                raise forms.ValidationError("The uploaded file is not a valid PDF document.")
            mime_type = "application/pdf"
        else:
            try:
                with Image.open(uploaded) as image:
                    image.verify()
                uploaded.seek(0)
                with Image.open(uploaded) as image:
                    if image.width * image.height > MAX_IMAGE_PIXELS:
                        raise forms.ValidationError("Image dimensions must not exceed 20 megapixels.")
                    image_format = image.format
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                raise forms.ValidationError("The uploaded file is not a valid JPG or PNG image.") from exc
            finally:
                uploaded.seek(0)

            expected_formats = {".jpg": {"JPEG"}, ".jpeg": {"JPEG"}, ".png": {"PNG"}}
            if image_format not in expected_formats[extension]:
                raise forms.ValidationError("The file extension does not match the image content.")
            mime_type = "image/jpeg" if image_format == "JPEG" else "image/png"

        uploaded.content_type = mime_type
        return uploaded


class MigrationSpreadsheetUploadForm(forms.Form):
    file = forms.FileField(help_text="Upload a CSV (.csv) or Excel (.xlsx) file, up to 5 MB.")

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        extension = PurePath(uploaded.name or "").suffix.lower()
        if extension not in ALLOWED_SPREADSHEET_EXTENSIONS:
            raise forms.ValidationError("Upload a CSV (.csv) or Excel (.xlsx) file.")
        if (uploaded.size or 0) > MAX_SPREADSHEET_SIZE:
            raise forms.ValidationError("Spreadsheet files must be 5 MB or smaller.")
        try:
            file_type, mime_type = detect_spreadsheet(uploaded)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        uploaded.file_type = file_type
        uploaded.content_type = mime_type
        return uploaded


class ColumnMappingForm(forms.Form):
    def __init__(self, *args, headers=None, initial_mapping=None, **kwargs):
        super().__init__(*args, **kwargs)
        headers = headers or []
        initial_mapping = initial_mapping or {}
        header_choices = [("", "— Not mapped —")] + [(h, h) for h in headers]
        for field, label in MAPPABLE_PATIENT_FIELDS.items():
            self.fields[f"map_{field}"] = forms.ChoiceField(
                label=label,
                choices=header_choices,
                required=False,
                initial=initial_mapping.get(field, ""),
            )

    def mapping(self):
        result = {}
        for field in MAPPABLE_PATIENT_FIELDS:
            value = (self.cleaned_data.get(f"map_{field}") or "").strip()
            if value:
                result[field] = value
        return result


class RecordDecisionForm(forms.Form):
    DECISION_CHOICES = [
        ("", "— Select decision —"),
        ("LINK_EXISTING", "Link to selected existing patient"),
        ("CREATE_NEW", "Mark as new patient"),
        ("FLAG", "Flag for further investigation"),
        ("REJECT", "Reject record"),
    ]

    decision = forms.ChoiceField(choices=DECISION_CHOICES, required=True)
    matched_patient_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Reason for decision (required for reject/flag)"}),
        label="Reason",
    )

    def clean(self):
        cleaned = super().clean()
        decision = cleaned.get("decision")
        reason = (cleaned.get("reason") or "").strip()
        matched = cleaned.get("matched_patient_id")
        if decision in {"REJECT", "FLAG"} and not reason:
            self.add_error("reason", "Provide a reason for this decision.")
        if decision == "LINK_EXISTING" and not matched:
            self.add_error("decision", "Select an existing patient to link this record.")
        cleaned["reason"] = reason
        return cleaned
