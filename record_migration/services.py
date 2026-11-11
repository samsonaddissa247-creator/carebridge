"""Digital spreadsheet parsing, validation, and staging helpers (Part 2).

Spreadsheet content is treated as untrusted data. Staging never creates or
updates Patient records.
"""
import csv
import io
from datetime import date, datetime
from pathlib import PurePath

from openpyxl import load_workbook

MAX_SPREADSHEET_SIZE = 5 * 1024 * 1024
MAX_SPREADSHEET_ROWS = 500
ALLOWED_SPREADSHEET_EXTENSIONS = {".csv", ".xlsx"}

# Real Patient model fields that may be imported from spreadsheets (Part 2: no
# patient creation/update is performed; these are staging/mapping targets only).
MAPPABLE_PATIENT_FIELDS = {
    "patient_id": "Patient number",
    "full_name": "Full name",
    "date_of_birth": "Date of birth",
    "sex": "Sex/Gender",
    "phone_number": "Phone number",
    "next_of_kin": "Next of kin",
    "allergies": "Allergies",
    "chronic_conditions": "Chronic conditions",
    "notes": "Notes",
}
REQUIRED_MAPPED_FIELDS = {"full_name", "date_of_birth", "sex"}


def detect_spreadsheet(uploaded):
    """Validate type/content/size; return (file_type, mime_type) or raise ValueError."""
    extension = PurePath(uploaded.name or "").suffix.lower()
    if extension not in ALLOWED_SPREADSHEET_EXTENSIONS:
        raise ValueError("Upload a CSV (.csv) or Excel (.xlsx) file.")
    size = getattr(uploaded, "size", 0) or 0
    if size > MAX_SPREADSHEET_SIZE:
        raise ValueError("Spreadsheet files must be 5 MB or smaller.")
    content = uploaded.read(MAX_SPREADSHEET_SIZE + 1)
    uploaded.seek(0)
    if len(content) > MAX_SPREADSHEET_SIZE:
        raise ValueError("Spreadsheet files must be 5 MB or smaller.")

    if extension == ".csv":
        if b"\x00" in content:
            raise ValueError("The uploaded file is not a valid CSV spreadsheet.")
        try:
            sample = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("CSV files must be UTF-8 encoded text.") from exc
        # Basic CSV parse sanity check
        try:
            reader = csv.reader(io.StringIO(sample))
            first = next(reader, None)
            if first is None:
                raise ValueError("The CSV file is empty.")
        except csv.Error as exc:
            raise ValueError("The uploaded CSV file is malformed.") from exc
        return "CSV", "text/csv"

    # XLSX: zip signature PK\x03\x04 and openpyxl-readable
    if not content.startswith(b"PK\x03\x04"):
        raise ValueError("The uploaded file is not a valid Excel (.xlsx) spreadsheet.")
    try:
        wb = load_workbook(filename=io.BytesIO(content), read_only=True, data_only=True)
        wb.close()
    except Exception as exc:  # noqa: BLE001 - untrusted file
        raise ValueError("The uploaded Excel file is malformed or unreadable.") from exc
    return "XLSX", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _normalize_header(value):
    return str(value).strip() if value is not None else ""


def _cell_to_str(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_spreadsheet_rows(stored_file_field):
    """Read headers and data rows from a stored CSV/XLSX FileField.

    Returns (headers:list[str], rows:list[dict[col->str]], total_count:int).
    """
    with stored_file_field.open("rb") as fh:
        data = fh.read()
    ext = PurePath(stored_file_field.name).suffix.lower()
    if ext == ".csv":
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        headers = [_normalize_header(h) for h in (reader.fieldnames or [])]
        if not any(headers):
            raise ValueError("The CSV file has no column headings.")
        rows = []
        for row in reader:
            rows.append({h: _cell_to_str(row.get(h, "")) for h in headers if h})
        return headers, rows, len(rows)

    wb = load_workbook(filename=io.BytesIO(data), read_only=True, data_only=True)
    try:
        ws = wb.active
        all_rows = list(ws.iter_rows(values_only=True))
        if not all_rows:
            raise ValueError("The spreadsheet is empty.")
        raw_headers = all_rows[0]
        headers = [_normalize_header(h) for h in raw_headers]
        if not any(headers):
            raise ValueError("The spreadsheet has no column headings.")
        rows = []
        for raw in all_rows[1:]:
            row_dict = {}
            for idx, header in enumerate(headers):
                if not header:
                    continue
                val = raw[idx] if idx < len(raw) else None
                row_dict[header] = _cell_to_str(val)
            rows.append(row_dict)
        return headers, rows, len(rows)
    finally:
        wb.close()


def normalize_sex(value):
    raw = (value or "").strip().lower()
    if raw in {"f", "female", "woman", "girl"}:
        return "F"
    if raw in {"m", "male", "man", "boy"}:
        return "M"
    return None


def parse_date_value(value):
    raw = (value or "").strip()
    if not raw:
        return None, "required"
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date(), None
        except ValueError:
            continue
    # ISO-like from excel already normalized
    try:
        return datetime.fromisoformat(raw).date(), None
    except ValueError:
        return None, "invalid"


def validate_and_stage_rows(source_file, rows, column_mapping):
    """Build staged record payloads for all rows (no Patient writes).

    column_mapping: {carelink_field: source_column_header or ""}.
    Returns list of dicts ready for MigrationRecord creation.
    """
    staged = []
    seen_signatures = set()
    for idx, row in enumerate(rows, start=2):  # header is row 1
        source_values = dict(row)
        mapped_values = {}
        errors = []
        # treat fully empty rows
        if not any((v or "").strip() for v in row.values()):
            staged.append(
                {
                    "row_number": idx,
                    "source_values": source_values,
                    "mapped_values": {},
                    "validation_status": "INVALID",
                    "validation_errors": ["Empty row."],
                    "is_duplicate_in_file": False,
                }
            )
            continue

        for field, source_col in (column_mapping or {}).items():
            if not source_col or field not in MAPPABLE_PATIENT_FIELDS:
                continue
            mapped_values[field] = (row.get(source_col, "") or "").strip()

        # Required fields
        for req in REQUIRED_MAPPED_FIELDS:
            if req not in mapped_values or not mapped_values.get(req):
                errors.append(f"Missing required field: {MAPPABLE_PATIENT_FIELDS.get(req, req)}.")

        # Date of birth
        dob_val = mapped_values.get("date_of_birth")
        if dob_val:
            parsed, err = parse_date_value(dob_val)
            if err == "invalid":
                errors.append(f"Invalid date of birth: '{dob_val}'.")
            elif parsed:
                if parsed > date.today():
                    errors.append("Date of birth cannot be in the future.")
                mapped_values["date_of_birth"] = parsed.isoformat()

        # Sex
        sex_val = mapped_values.get("sex")
        if sex_val:
            norm = normalize_sex(sex_val)
            if norm is None:
                errors.append(f"Invalid sex/gender value: '{sex_val}'.")
            else:
                mapped_values["sex"] = norm

        # patient_id format sanity (if provided)
        pid = mapped_values.get("patient_id")
        if pid and len(pid) > 12:
            errors.append("Patient number is too long.")

        # phone length
        phone = mapped_values.get("phone_number")
        if phone and len(phone) > 20:
            errors.append("Phone number is too long.")

        # Duplicate rows within spreadsheet (by stable signature of mapped core fields)
        sig = (
            (mapped_values.get("patient_id") or "").lower(),
            (mapped_values.get("full_name") or "").lower(),
            (mapped_values.get("date_of_birth") or ""),
            (mapped_values.get("sex") or ""),
            (mapped_values.get("phone_number") or ""),
        )
        is_dup = sig in seen_signatures
        if any(sig):
            seen_signatures.add(sig)
        if is_dup:
            errors.append("Duplicate row within the uploaded spreadsheet.")

        # Part 2: possible-duplicate vs existing patients NOT computed (Part 3).
        if errors:
            status = "INVALID"
        elif is_dup:
            status = "INVALID"
        else:
            status = "VALID"

        staged.append(
            {
                "row_number": idx,
                "source_values": source_values,
                "mapped_values": mapped_values,
                "validation_status": status,
                "validation_errors": errors,
                "is_duplicate_in_file": bool(is_dup),
            }
        )
    return staged


def summarize_staged(records_qs):
    total = records_qs.count()
    valid = records_qs.filter(validation_status="VALID").count()
    invalid = records_qs.filter(validation_status="INVALID").count()
    empty = sum(
        1
        for errs in records_qs.values_list("validation_errors", flat=True)
        if "Empty row." in (errs or [])
    )
    possible = records_qs.filter(validation_status="POSSIBLE_DUPLICATE").count()
    awaiting = records_qs.filter(
        validation_status__in=["PENDING_REVIEW", "VALID", "POSSIBLE_DUPLICATE", "READY_FOR_APPROVAL"]
    ).count()
    return {
        "total": total,
        "valid": valid,
        "invalid": invalid,
        "empty": empty,
        "possible_duplicates": possible,
        "awaiting_approval": awaiting,
    }


def batch_report_data(batch):
    """Compute batch report statistics from actual database records."""
    from .models import MigrationAuditLog, MigrationRecord

    docs = batch.documents.all()
    files = batch.files.all()
    records = MigrationRecord.objects.filter(batch=batch)
    total_files = docs.count() + files.count()
    # Total records processed: staged digital rows, or paper documents
    staged_total = records.count()
    total_processed = staged_total if batch.migration_type == "DIGITAL" else docs.count()
    imported = records.filter(is_imported=True).count()
    rejected = records.filter(review_status=MigrationRecord.ReviewStatus.REJECTED).count()
    invalid = records.filter(validation_status=MigrationRecord.ValidationStatus.INVALID).count()
    possible_dupes = records.filter(
        review_status=MigrationRecord.ReviewStatus.POSSIBLE_DUPLICATE
    ).count() + records.filter(is_duplicate_in_file=True).exclude(
        review_status=MigrationRecord.ReviewStatus.POSSIBLE_DUPLICATE
    ).count()
    awaiting = records.filter(is_imported=False).exclude(
        review_status__in=[MigrationRecord.ReviewStatus.REJECTED]
    ).exclude(validation_status=MigrationRecord.ValidationStatus.INVALID).count()

    # completed date: latest import or approval completion activity
    completed_at = None
    last_import = records.filter(imported_at__isnull=False).order_by("-imported_at").values_list("imported_at", flat=True).first()
    if batch.status in {"COMPLETED", "APPROVED"} and last_import:
        completed_at = last_import
    elif batch.status == "COMPLETED":
        completed_at = batch.audit_logs.order_by("-created_at").values_list("created_at", flat=True).first()

    reviewers = (
        MigrationAuditLog.objects.filter(batch=batch, actor__isnull=False)
        .filter(action__in=["match_decision_saved", "record_approved", "record_imported"])
        .select_related("actor")
        .order_by("actor_id", "-created_at")
    )
    seen = set()
    reviewer_list = []
    for log in reviewers:
        if log.actor_id and log.actor_id not in seen:
            seen.add(log.actor_id)
            reviewer_list.append(log.actor)

    return {
        "total_files": total_files,
        "total_records_processed": total_processed,
        "imported": imported,
        "rejected": rejected,
        "invalid": invalid,
        "possible_duplicates": possible_dupes,
        "awaiting_review": awaiting,
        "completed_at": completed_at,
        "reviewers": reviewer_list,
    }


def batch_error_rows(batch):
    """Rows for error reporting/download (no unnecessary patient info)."""
    from .models import MigrationRecord

    rows = []
    for rec in MigrationRecord.objects.filter(batch=batch).select_related("source_file").order_by("source_file_id", "row_number"):
        issues = []
        if rec.validation_status == "INVALID" or rec.validation_errors:
            for e in (rec.validation_errors or []):
                issues.append(("Validation error", e, "Unresolved" if not rec.is_imported else "Superseded"))
        if rec.is_duplicate_in_file:
            issues.append(("Duplicate in file", "Duplicate row within the uploaded spreadsheet.", "Unresolved" if not rec.is_imported else "Superseded"))
        if rec.review_status == rec.ReviewStatus.POSSIBLE_DUPLICATE or any("duplicate" in str(c).lower() for c in (rec.conflicts or [])):
            for c in (rec.conflicts or ["Possible duplicate record."]):
                if "duplicate" in str(c).lower() or rec.review_status == rec.ReviewStatus.POSSIBLE_DUPLICATE:
                    issues.append(("Possible duplicate", c, "Resolved" if rec.is_imported or rec.review_status == rec.ReviewStatus.REJECTED else "Awaiting review"))
        if rec.import_error:
            issues.append(("Import error", rec.import_error, "Resolved" if rec.is_imported else "Unresolved"))
        for error_type, description, resolution in issues:
            rows.append({
                "row_number": rec.row_number,
                "source_file": rec.source_file.original_filename if rec.source_file else "",
                "error_type": error_type,
                "description": description,
                "resolution_status": resolution,
                "review_status": rec.get_review_status_display(),
            })
    return rows

# -------------------- Part 3: matching, review, approval, import --------------------
from django.db import transaction
from django.utils import timezone

from patients.models import Patient


def _parse_iso_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except Exception:
        try:
            d, _ = parse_date_value(str(value))
            return d
        except Exception:
            return None


def detect_patient_matches(mapped_values, record=None, batch=None):
    """Return (candidates, review_status, conflicts, notes).

    Candidates are non-sensitive identifying summaries for authorised staff.
    Never auto-merge; names/DOB are suggestions only.
    """
    candidates = []
    notes = []
    conflicts = []
    pid = (mapped_values.get("patient_id") or "").strip()
    full_name = (mapped_values.get("full_name") or "").strip()
    dob = _parse_iso_date(mapped_values.get("date_of_birth"))
    sex = (mapped_values.get("sex") or "").strip()

    # Reliable unique identifier: existing hospital patient number
    exact = None
    if pid:
        exact = Patient.objects.filter(patient_id__iexact=pid).first()
        if exact:
            candidates.append(
                {
                    "patient_id": exact.pk,
                    "patient_number": exact.patient_id,
                    "full_name": exact.full_name,
                    "date_of_birth": exact.date_of_birth.isoformat() if exact.date_of_birth else "",
                    "sex": exact.sex,
                    "reason": "Exact hospital patient number match",
                    "strength": "exact",
                }
            )
            conflicts.extend(compare_patient_conflicts(exact, mapped_values))

    # Name + DOB suggestion (not reliable alone)
    if full_name and dob:
        qs = Patient.objects.filter(full_name__iexact=full_name, date_of_birth=dob)
        if sex:
            qs = qs.filter(sex=sex)
        if exact:
            qs = qs.exclude(pk=exact.pk)
        for p in qs[:5]:
            candidates.append(
                {
                    "patient_id": p.pk,
                    "patient_number": p.patient_id,
                    "full_name": p.full_name,
                    "date_of_birth": p.date_of_birth.isoformat() if p.date_of_birth else "",
                    "sex": p.sex,
                    "reason": "Possible match: same name and date of birth",
                    "strength": "suggested",
                }
            )

    # Detect if already staged/imported elsewhere in system/batch (by patient number if known)
    if pid:
        from record_migration.models import MigrationRecord

        imported_elsewhere = MigrationRecord.objects.filter(
            mapped_values__patient_id=pid, is_imported=True
        )
        if record and record.pk:
            imported_elsewhere = imported_elsewhere.exclude(pk=record.pk)
        if imported_elsewhere.exists():
            conflicts.append("A staged record with this patient number was already imported.")
            notes.append("Possible already imported record detected.")

    # in-file duplicate already flagged at staging
    if record and getattr(record, "is_duplicate_in_file", False):
        conflicts.append("Duplicate row within the uploaded spreadsheet.")
        notes.append("Duplicate row in batch.")

    # Determine suggested review status (staff must confirm)
    exact_ids = [c["patient_id"] for c in candidates if c.get("strength") == "exact"]
    suggested_ids = [c["patient_id"] for c in candidates if c.get("strength") == "suggested"]
    if exact_ids or any(c.get("strength") == "suggested" for c in candidates):
        # any match requires human review; exact is a strong existing-patient match
        if exact_ids and len(exact_ids) == 1 and not suggested_ids and not conflicts:
            review_status = "EXISTING_PATIENT_MATCH"
        else:
            review_status = "POSSIBLE_DUPLICATE"
    elif conflicts:
        review_status = "NEEDS_REVIEW"
    else:
        review_status = "NEW_PATIENT"

    # De-duplicate candidate entries by patient
    uniq = {}
    for c in candidates:
        key = c["patient_id"]
        if key not in uniq or (c.get("strength") == "exact" and uniq[key].get("strength") != "exact"):
            uniq[key] = c
    return list(uniq.values()), review_status, conflicts, notes


def compare_patient_conflicts(patient, mapped_values):
    """Return list of conflict descriptions when mapped values differ from existing patient.

    Never overwrite silently; conflicts are flagged for review.
    """
    conflicts = []
    comparisons = [
        ("full_name", "Full name"),
        ("date_of_birth", "Date of birth"),
        ("sex", "Sex"),
        ("phone_number", "Phone number"),
        ("next_of_kin", "Next of kin"),
    ]
    for field, label in comparisons:
        incoming = (mapped_values.get(field) or "").strip()
        if not incoming:
            continue
        existing = getattr(patient, field, "")
        if field == "date_of_birth":
            incoming_d = _parse_iso_date(incoming)
            if incoming_d and existing and incoming_d != existing:
                conflicts.append(f"{label} differs: existing '{existing}', imported '{incoming_d.isoformat()}'.")
            continue
        if str(existing).strip() and str(existing).strip().lower() != incoming.lower():
            conflicts.append(f"{label} differs: existing '{str(existing).strip()}', imported '{incoming}'.")
    return conflicts


def run_matching_for_batch(batch):
    from record_migration.models import MigrationRecord

    records = MigrationRecord.objects.filter(batch=batch).select_related("source_file")
    updated = 0
    for rec in records:
        if rec.is_imported or rec.validation_status == MigrationRecord.ValidationStatus.INVALID:
            continue
        candidates, suggested_status, conflicts, notes = detect_patient_matches(
            rec.mapped_values or {}, record=rec, batch=batch
        )
        rec.match_candidates = candidates
        rec.conflicts = conflicts
        # Preserve explicit human decisions/rejections/approvals where appropriate
        if rec.review_status not in {
            MigrationRecord.ReviewStatus.REJECTED,
            MigrationRecord.ReviewStatus.READY_FOR_APPROVAL,
            MigrationRecord.ReviewStatus.IMPORTED,
        }:
            if rec.decision == MigrationRecord.Decision.FLAG:
                rec.review_status = MigrationRecord.ReviewStatus.NEEDS_REVIEW
            elif rec.decision == MigrationRecord.Decision.REJECT:
                rec.review_status = MigrationRecord.ReviewStatus.REJECTED
            elif rec.decision in {MigrationRecord.Decision.LINK_EXISTING, MigrationRecord.Decision.CREATE_NEW} and rec.matched_patient_id and rec.decision == MigrationRecord.Decision.LINK_EXISTING:
                rec.review_status = suggested_status if suggested_status == "POSSIBLE_DUPLICATE" else MigrationRecord.ReviewStatus.EXISTING_PATIENT_MATCH
            elif rec.decision == MigrationRecord.Decision.CREATE_NEW:
                rec.review_status = suggested_status if suggested_status == "POSSIBLE_DUPLICATE" else MigrationRecord.ReviewStatus.NEW_PATIENT
            else:
                rec.review_status = suggested_status
        rec.save(update_fields=["match_candidates", "conflicts", "review_status"])
        updated += 1
    return updated


def can_approve_record(record, user):
    if not record:
        return False, "Record not found."
    if record.is_imported:
        return False, "This record has already been imported."
    if record.validation_status == "INVALID":
        return False, "Invalid records cannot be approved."
    if record.review_status == "REJECTED" or record.decision == "REJECT":
        return False, "Rejected records cannot be approved."
    if record.conflicts:
        return False, "Resolve or acknowledge flagged conflicts before approval."
    if record.review_status == "POSSIBLE_DUPLICATE":
        return False, "Possible duplicate matches must be reviewed and resolved before approval."
    if record.decision == "LINK_EXISTING":
        if not record.matched_patient_id:
            return False, "Select an existing patient before approval."
    elif record.decision == "CREATE_NEW":
        required = {"full_name", "date_of_birth", "sex"}
        missing = [f for f in required if not (record.mapped_values or {}).get(f)]
        if missing:
            return False, "Missing required information for new patient creation."
    else:
        return False, "Select an existing patient or mark as a new patient before approval."
    # Independent approval: uploader of the source file cannot self-approve when known
    if user and record.source_file and record.source_file.uploaded_by_id and user.pk == record.source_file.uploaded_by_id:
        # allow if there is no other reviewer context? enforce separate reviewer when possible
        # (admin may still be blocked by this rule; relaxed only if uploader is the sole actor - checked in view)
        return False, "A separate reviewer must approve records uploaded by you."
    return True, ""


def build_patient_from_mapped(mapped_values, registered_by=None):
    data = {
        "full_name": (mapped_values.get("full_name") or "").strip(),
        "date_of_birth": _parse_iso_date(mapped_values.get("date_of_birth")),
        "sex": (mapped_values.get("sex") or "").strip(),
        "phone_number": (mapped_values.get("phone_number") or "").strip()[:20],
        "next_of_kin": (mapped_values.get("next_of_kin") or "").strip()[:150],
        "allergies": (mapped_values.get("allergies") or "").strip()[:255],
        "chronic_conditions": (mapped_values.get("chronic_conditions") or "").strip()[:255],
        "notes": (mapped_values.get("notes") or "").strip(),
        "registered_by": registered_by,
    }
    return data


@transaction.atomic
def import_staged_record(record_id, user):
    from record_migration.models import MigrationAuditLog, MigrationRecord

    record = (
        MigrationRecord.objects.select_for_update()
        .select_related("batch", "source_file", "matched_patient")
        .get(pk=record_id)
    )
    if record.is_imported:
        return False, "This record has already been imported.", None
    if record.validation_status == "INVALID":
        return False, "Invalid records cannot be imported.", None
    if record.review_status != MigrationRecord.ReviewStatus.READY_FOR_APPROVAL:
        return False, "Record must be ready for approval before import.", None
    if not record.approved_by_id or not record.approved_at:
        return False, "Record must be approved before import.", None
    if record.conflicts:
        return False, "Conflicting information must be resolved before import.", None

    mapped = record.mapped_values or {}
    target_patient = None
    created_new = False

    if record.decision == MigrationRecord.Decision.LINK_EXISTING:
        if not record.matched_patient_id:
            return False, "No existing patient selected.", None
        # lock existing patient row
        target_patient = Patient.objects.select_for_update().get(pk=record.matched_patient_id)
        # Never silently overwrite: flag if conflicts exist (re-check)
        conflicts = compare_patient_conflicts(target_patient, mapped)
        if conflicts:
            record.conflicts = conflicts
            record.review_status = MigrationRecord.ReviewStatus.NEEDS_REVIEW
            record.import_error = "Conflicting patient information detected; import blocked."
            record.save(update_fields=["conflicts", "review_status", "import_error"])
            return False, "Conflicting patient information detected; record flagged for review.", None
    elif record.decision == MigrationRecord.Decision.CREATE_NEW:
        data = build_patient_from_mapped(mapped, registered_by=user)
        # prevent duplicate by patient number if provided
        pid = (mapped.get("patient_id") or "").strip()
        if pid:
            existing = Patient.objects.select_for_update().filter(patient_id__iexact=pid).first()
            if existing:
                record.matched_patient = existing
                record.review_status = MigrationRecord.ReviewStatus.POSSIBLE_DUPLICATE
                record.import_error = "Patient number already exists; linked record requires review."
                record.save(update_fields=["matched_patient", "review_status", "import_error"])
                return False, "A patient with this patient number already exists.", None
        # prevent duplicate by core identity
        dob = data.get("date_of_birth")
        existing_identity = Patient.objects.select_for_update().filter(
            full_name__iexact=data["full_name"], date_of_birth=dob, sex=data["sex"]
        ).first()
        if existing_identity:
            record.matched_patient = existing_identity
            record.review_status = MigrationRecord.ReviewStatus.POSSIBLE_DUPLICATE
            record.import_error = "Possible existing patient found; record requires review."
            record.save(update_fields=["matched_patient", "review_status", "import_error"])
            return False, "A possible existing patient already matches these details.", None
        # Note: Patient.patient_id is auto-generated unique; we do not override it.
        target_patient = Patient.objects.create(**data)
        created_new = True
    else:
        return False, "No valid import decision recorded.", None

    record.is_imported = True
    record.imported_patient = target_patient
    record.imported_by = user
    record.imported_at = timezone.now()
    record.review_status = MigrationRecord.ReviewStatus.IMPORTED
    record.import_error = ""
    record.save(
        update_fields=[
            "is_imported", "imported_patient", "imported_by", "imported_at",
            "review_status", "import_error", "matched_patient",
        ]
    )

    # mark batch completed when all non-invalid/rejected records imported? leave conservative
    MigrationAuditLog.objects.create(
        batch=record.batch,
        source_file=record.source_file,
        record=record,
        actor=user,
        action="record_imported",
        details=(
            f"Imported row {record.row_number} as {'new' if created_new else 'linked'} "
            f"patient {target_patient.patient_id} (pk={target_patient.pk})."
        ),
    )
    return True, "Record imported successfully.", target_patient
