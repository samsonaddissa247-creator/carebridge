import uuid
from pathlib import PurePosixPath

from django.conf import settings
from django.db import models

from patients.models import Patient


def migration_document_path(instance, filename):
    extension = PurePosixPath(filename).suffix.lower()
    identifier = uuid.uuid4().hex
    return f"patient-migration/{identifier[:2]}/{identifier}{extension}"


def migration_spreadsheet_path(instance, filename):
    extension = PurePosixPath(filename).suffix.lower()
    identifier = uuid.uuid4().hex
    return f"patient-migration/digital/{identifier[:2]}/{identifier}{extension}"


class MigrationBatch(models.Model):
    class MigrationType(models.TextChoices):
        PAPER = "PAPER", "Paper records"
        DIGITAL = "DIGITAL", "Digital records"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        UPLOADED = "UPLOADED", "Uploaded"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        APPROVED = "APPROVED", "Approved"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    name = models.CharField(max_length=150)
    migration_type = models.CharField(max_length=10, choices=MigrationType.choices)
    source_hospital = models.CharField(max_length=150, blank=True)
    source_department = models.CharField(max_length=150, blank=True)
    source_system = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="patient_migration_batches",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class MigrationDocument(models.Model):
    batch = models.ForeignKey(MigrationBatch, on_delete=models.CASCADE, related_name="documents")
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="migration_documents")
    file = models.FileField(upload_to=migration_document_path)
    original_filename = models.CharField(max_length=255)
    document_date = models.DateField()
    source = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    mime_type = models.CharField(max_length=50)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="patient_migration_documents",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.original_filename} for {self.patient.patient_id}"


class MigrationFile(models.Model):
    """Uploaded CSV/XLSX spreadsheet for a digital migration batch."""

    class FileType(models.TextChoices):
        CSV = "CSV", "CSV"
        XLSX = "XLSX", "Excel (XLSX)"

    batch = models.ForeignKey(MigrationBatch, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to=migration_spreadsheet_path)
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=10, choices=FileType.choices)
    mime_type = models.CharField(max_length=100)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="patient_migration_files",
    )
    row_count = models.PositiveIntegerField(default=0)
    column_headers = models.JSONField(default=list, blank=True)
    column_mapping = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.batch.name})"


class MigrationRecord(models.Model):
    """Staged spreadsheet row awaiting review/approval. Never a permanent patient record."""

    class ValidationStatus(models.TextChoices):
        PENDING_REVIEW = "PENDING_REVIEW", "Pending Review"
        VALID = "VALID", "Valid"
        INVALID = "INVALID", "Invalid"
        POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE", "Possible Duplicate"
        READY_FOR_APPROVAL = "READY_FOR_APPROVAL", "Ready for Approval"

    class ReviewStatus(models.TextChoices):
        NEW_PATIENT = "NEW_PATIENT", "New Patient"
        EXISTING_PATIENT_MATCH = "EXISTING_PATIENT_MATCH", "Existing Patient Match"
        POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE", "Possible Duplicate"
        NEEDS_REVIEW = "NEEDS_REVIEW", "Needs Review"
        READY_FOR_APPROVAL = "READY_FOR_APPROVAL", "Ready for Approval"
        REJECTED = "REJECTED", "Rejected"
        IMPORTED = "IMPORTED", "Imported"

    class Decision(models.TextChoices):
        NONE = "NONE", "No decision"
        LINK_EXISTING = "LINK_EXISTING", "Link to existing patient"
        CREATE_NEW = "CREATE_NEW", "Create new patient"
        FLAG = "FLAG", "Flag for investigation"
        REJECT = "REJECT", "Reject record"

    batch = models.ForeignKey(MigrationBatch, on_delete=models.CASCADE, related_name="records")
    source_file = models.ForeignKey(MigrationFile, on_delete=models.CASCADE, related_name="records")
    row_number = models.PositiveIntegerField()
    source_values = models.JSONField(default=dict)
    mapped_values = models.JSONField(default=dict, blank=True)
    validation_status = models.CharField(
        max_length=30, choices=ValidationStatus.choices, default=ValidationStatus.PENDING_REVIEW
    )
    validation_errors = models.JSONField(default=list, blank=True)
    is_duplicate_in_file = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Part 3: matching / review / approval / import
    review_status = models.CharField(
        max_length=30, choices=ReviewStatus.choices, default=ReviewStatus.NEEDS_REVIEW
    )
    match_candidates = models.JSONField(default=list, blank=True)
    matched_patient = models.ForeignKey(
        Patient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_match_records",
    )
    conflicts = models.JSONField(default=list, blank=True)
    decision = models.CharField(max_length=20, choices=Decision.choices, default=Decision.NONE)
    decision_reason = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_decisions_made",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_records_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    is_imported = models.BooleanField(default=False)
    imported_patient = models.ForeignKey(
        Patient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_imported_records",
    )
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="migration_records_imported",
    )
    imported_at = models.DateTimeField(null=True, blank=True)
    import_error = models.TextField(blank=True)

    class Meta:
        ordering = ["source_file_id", "row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "source_file", "row_number"],
                name="unique_staged_row_per_file",
            )
        ]

    def __str__(self):
        return f"Row {self.row_number} ({self.source_file.original_filename})"


class MigrationAuditLog(models.Model):
    batch = models.ForeignKey(
        MigrationBatch,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    document = models.ForeignKey(
        MigrationDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    source_file = models.ForeignKey(
        MigrationFile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    record = models.ForeignKey(
        MigrationRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="patient_migration_actions",
    )
    action = models.CharField(max_length=50)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.batch.name}: {self.action}"
