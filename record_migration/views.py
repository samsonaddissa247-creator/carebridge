import csv
from pathlib import PurePath

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.models import User
from patients.models import Patient
from patients.permissions import doctor_patient_queryset

from .forms import (
    ColumnMappingForm,
    MigrationBatchForm,
    MigrationDocumentForm,
    MigrationSpreadsheetUploadForm,
    RecordDecisionForm,
)
from .models import MigrationAuditLog, MigrationBatch, MigrationDocument, MigrationFile, MigrationRecord
from .permissions import accessible_batches, can_access_batch, can_view_migrations
from .services import (
    MAX_SPREADSHEET_ROWS,
    batch_error_rows,
    batch_report_data,
    can_approve_record,
    import_staged_record,
    read_spreadsheet_rows,
    run_matching_for_batch,
    summarize_staged,
    validate_and_stage_rows,
)


def _record_migration_action(batch, actor, action, document=None, source_file=None, record=None, details=""):
    MigrationAuditLog.objects.create(
        batch=batch,
        document=document,
        source_file=source_file,
        record=record,
        actor=actor,
        action=action,
        details=details,
    )


def _refresh_batch_status(batch):
    qs = batch.records.all()
    if not qs.exists():
        return
    statuses = set(qs.values_list("review_status", flat=True))
    if statuses and statuses.issubset({MigrationRecord.ReviewStatus.IMPORTED, MigrationRecord.ReviewStatus.REJECTED}):
        new_status = MigrationBatch.Status.COMPLETED
    elif MigrationRecord.ReviewStatus.READY_FOR_APPROVAL in statuses or MigrationRecord.ReviewStatus.IMPORTED in statuses:
        new_status = MigrationBatch.Status.APPROVED
    else:
        new_status = MigrationBatch.Status.UNDER_REVIEW
    if batch.status != new_status:
        batch.status = new_status
        batch.save(update_fields=["status"])


@login_required
@require_GET
def dashboard(request):
    if not can_view_migrations(request.user):
        return HttpResponseForbidden("You are not authorised to access patient record migration.")

    batches = accessible_batches(request.user).annotate(
        document_count=Count("documents", distinct=True),
        file_count=Count("files", distinct=True),
        staged_count=Count("records", distinct=True),
        imported_count=Count("records", filter=Q(records__is_imported=True), distinct=True),
    )
    documents = MigrationDocument.objects.filter(batch__in=batches)
    if request.user.role == User.Role.DOCTOR:
        documents = documents.filter(patient__in=doctor_patient_queryset(request.user))
    staged = MigrationRecord.objects.filter(batch__in=batches)

    total_processed = documents.count() + staged.count()
    awaiting_review = documents.filter(
        batch__status__in=[MigrationBatch.Status.UPLOADED, MigrationBatch.Status.UNDER_REVIEW]
    ).count() + staged.filter(is_imported=False).exclude(
        review_status__in=[MigrationRecord.ReviewStatus.REJECTED, MigrationRecord.ReviewStatus.IMPORTED]
    ).exclude(validation_status=MigrationRecord.ValidationStatus.INVALID).count()
    successfully_imported = staged.filter(is_imported=True).count()
    rejected_records = staged.filter(review_status=MigrationRecord.ReviewStatus.REJECTED).count()
    records_with_errors = batches.filter(status=MigrationBatch.Status.FAILED).count() + staged.filter(
        Q(validation_status=MigrationRecord.ValidationStatus.INVALID) | Q(import_error__gt="")
    ).exclude(is_imported=True).count()
    possible_duplicates = staged.filter(
        Q(review_status=MigrationRecord.ReviewStatus.POSSIBLE_DUPLICATE) | Q(is_duplicate_in_file=True)
    ).distinct().count()

    recent_activities = MigrationAuditLog.objects.filter(batch__in=batches).select_related(
        "actor", "batch"
    )[:10]
    return render(
        request,
        "record_migration/dashboard.html",
        {
            "batches": batches.select_related("created_by")[:20],
            "total_batches": batches.count(),
            "total_files": documents.count() + MigrationFile.objects.filter(batch__in=batches).count(),
            "total_records_processed": total_processed,
            "records_awaiting_review": awaiting_review,
            "successfully_imported": successfully_imported,
            "rejected_records": rejected_records,
            "records_with_errors": records_with_errors,
            "possible_duplicates": possible_duplicates,
            "recent_activities": recent_activities,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def create_batch(request):
    if not can_view_migrations(request.user):
        return HttpResponseForbidden("You are not authorised to create migration batches.")

    form = MigrationBatchForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            batch = form.save(commit=False)
            batch.created_by = request.user
            batch.save()
            _record_migration_action(batch, request.user, "batch_created")
        if batch.migration_type == MigrationBatch.MigrationType.PAPER:
            return redirect("record_migration:upload_document", batch_id=batch.pk)
        return redirect("record_migration:upload_spreadsheet", batch_id=batch.pk)
    return render(request, "record_migration/create_batch.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def upload_document(request, batch_id):
    batch = get_object_or_404(MigrationBatch, pk=batch_id)
    if not can_access_batch(request.user, batch):
        return HttpResponseForbidden("You are not authorised to upload to this migration batch.")
    if batch.migration_type != MigrationBatch.MigrationType.PAPER:
        return HttpResponseForbidden("This upload form only accepts paper-record documents.")
    if getattr(settings, "IS_VERCEL", False):
        return HttpResponseForbidden(
            "Private document uploads are unavailable on this hosting setup. Use persistent private file storage first."
        )

    form = MigrationDocumentForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        uploaded = form.cleaned_data["file"]
        safe_name = PurePath(uploaded.name.replace("\\", "/")).name[:255]
        with transaction.atomic():
            document = MigrationDocument.objects.create(
                batch=batch,
                patient=form.cleaned_data["patient"],
                file=uploaded,
                original_filename=safe_name,
                document_date=form.cleaned_data["document_date"],
                source=form.cleaned_data["source"].strip(),
                description=form.cleaned_data["description"].strip(),
                mime_type=uploaded.content_type,
                uploaded_by=request.user,
            )
            if batch.status == MigrationBatch.Status.DRAFT:
                batch.status = MigrationBatch.Status.UPLOADED
                batch.save(update_fields=["status"])
            _record_migration_action(
                batch,
                request.user,
                "document_uploaded",
                document=document,
                details="Scanned document attached to an existing patient profile.",
            )
        return redirect("record_migration:dashboard")
    return render(request, "record_migration/upload_document.html", {"batch": batch, "form": form})


@login_required
@require_http_methods(["GET", "POST"])
def upload_spreadsheet(request, batch_id):
    batch = get_object_or_404(MigrationBatch, pk=batch_id)
    if not can_access_batch(request.user, batch):
        return HttpResponseForbidden("You are not authorised to upload to this migration batch.")
    if batch.migration_type != MigrationBatch.MigrationType.DIGITAL:
        return HttpResponseForbidden("This upload form only accepts digital spreadsheet files.")
    if getattr(settings, "IS_VERCEL", False):
        return HttpResponseForbidden(
            "Private file uploads are unavailable on this hosting setup. Use persistent private file storage first."
        )

    existing = batch.files.select_related("uploaded_by").order_by("-created_at")
    form = MigrationSpreadsheetUploadForm(request.POST or None, request.FILES or None)
    upload_error = None
    if request.method == "POST" and form.is_valid():
        uploaded = form.cleaned_data["file"]
        safe_name = PurePath(uploaded.name.replace("\\", "/")).name[:255]
        try:
            headers, rows, total = _read_uploaded_rows(uploaded, uploaded.file_type)
            if total > MAX_SPREADSHEET_ROWS:
                raise ValueError(f"Spreadsheets may contain at most {MAX_SPREADSHEET_ROWS} data rows.")
        except ValueError as exc:
            upload_error = str(exc)
        else:
            with transaction.atomic():
                if batch.status == MigrationBatch.Status.DRAFT:
                    for old in batch.files.all():
                        old.file.delete(save=False)
                    batch.files.all().delete()
                    batch.records.all().delete()
                source_file = MigrationFile.objects.create(
                    batch=batch,
                    file=uploaded,
                    original_filename=safe_name,
                    file_type=uploaded.file_type,
                    mime_type=uploaded.content_type,
                    uploaded_by=request.user,
                    row_count=total,
                    column_headers=headers,
                )
                if batch.status == MigrationBatch.Status.DRAFT:
                    batch.status = MigrationBatch.Status.UPLOADED
                    batch.save(update_fields=["status"])
                _record_migration_action(
                    batch,
                    request.user,
                    "spreadsheet_uploaded",
                    source_file=source_file,
                    details=f"Spreadsheet uploaded ({source_file.file_type}, {total} data row(s)).",
                )
            return redirect("record_migration:spreadsheet_preview", batch_id=batch.pk, file_id=source_file.pk)

    return render(
        request,
        "record_migration/upload_spreadsheet.html",
        {"batch": batch, "form": form, "existing_files": existing, "upload_error": upload_error},
    )


def _read_uploaded_rows(uploaded, file_type):
    import csv
    import io
    from openpyxl import load_workbook

    uploaded.seek(0)
    data = uploaded.read()
    uploaded.seek(0)
    if file_type == "CSV":
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        headers = [str(h).strip() for h in (reader.fieldnames or []) if str(h).strip()]
        if not headers:
            raise ValueError("The CSV file has no column headings.")
        rows = []
        for row in reader:
            rows.append({h: (str(row.get(h, "")).strip() if row.get(h) is not None else "") for h in headers})
        return headers, rows, len(rows)
    wb = load_workbook(filename=io.BytesIO(data), read_only=True, data_only=True)
    try:
        ws = wb.active
        all_rows = list(ws.iter_rows(values_only=True))
        if not all_rows:
            raise ValueError("The spreadsheet is empty.")
        headers = [str(h).strip() if h is not None else "" for h in all_rows[0]]
        headers = [h for h in headers if h]
        if not headers:
            raise ValueError("The spreadsheet has no column headings.")
        rows = []
        for raw in all_rows[1:]:
            row_dict = {}
            for idx, header in enumerate([str(h).strip() if h is not None else "" for h in all_rows[0]]):
                if not header:
                    continue
                val = raw[idx] if idx < len(raw) else None
                if val is None:
                    sval = ""
                else:
                    from datetime import date, datetime
                    if isinstance(val, datetime):
                        sval = val.date().isoformat()
                    elif isinstance(val, date):
                        sval = val.isoformat()
                    elif isinstance(val, float) and val.is_integer():
                        sval = str(int(val))
                    else:
                        sval = str(val).strip()
                row_dict[header] = sval
            rows.append(row_dict)
        return headers, rows, len(rows)
    finally:
        wb.close()


@login_required
@require_GET
def spreadsheet_preview(request, batch_id, file_id):
    batch = get_object_or_404(MigrationBatch, pk=batch_id)
    if not can_access_batch(request.user, batch):
        return HttpResponseForbidden("You are not authorised to access this migration batch.")
    source_file = get_object_or_404(MigrationFile, pk=file_id, batch=batch)
    try:
        headers, rows, total = read_spreadsheet_rows(source_file.file)
    except Exception:  # noqa: BLE001
        return render(
            request,
            "record_migration/spreadsheet_preview.html",
            {
                "batch": batch, "source_file": source_file, "headers": [], "preview_rows": [],
                "total_rows": source_file.row_count, "empty_field_count": 0,
                "read_error": "The stored spreadsheet could not be read. It may be malformed.",
            },
        )
    preview_rows = rows[:20]
    empty_field_count = sum(1 for r in rows for v in r.values() if not (v or "").strip())
    for r in preview_rows:
        r["preview_issues"] = [f"Empty: {k}" for k, v in r.items() if not (v or "").strip()]
    return render(
        request,
        "record_migration/spreadsheet_preview.html",
        {
            "batch": batch, "source_file": source_file, "headers": headers,
            "preview_rows": preview_rows, "total_rows": total,
            "empty_field_count": empty_field_count, "read_error": None,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def column_mapping(request, batch_id, file_id):
    batch = get_object_or_404(MigrationBatch, pk=batch_id)
    if not can_access_batch(request.user, batch):
        return HttpResponseForbidden("You are not authorised to access this migration batch.")
    source_file = get_object_or_404(MigrationFile, pk=file_id, batch=batch)
    headers = source_file.column_headers or []
    if not headers:
        try:
            headers, _, _ = read_spreadsheet_rows(source_file.file)
        except Exception:  # noqa: BLE001
            headers = []

    form = ColumnMappingForm(request.POST or None, headers=headers, initial_mapping=source_file.column_mapping or {})
    saved = False
    if request.method == "POST" and form.is_valid():
        mapping = form.mapping()
        if "save_mapping" in request.POST:
            source_file.column_mapping = mapping
            source_file.save(update_fields=["column_mapping"])
            _record_migration_action(
                batch, request.user, "column_mapping_saved", source_file=source_file,
                details=f"Column mapping saved ({len(mapping)} mapped field(s)).",
            )
            saved = True
        elif "validate_stage" in request.POST:
            try:
                _, rows, total = read_spreadsheet_rows(source_file.file)
                if total > MAX_SPREADSHEET_ROWS:
                    raise ValueError(f"Spreadsheets may contain at most {MAX_SPREADSHEET_ROWS} data rows.")
                staged_payloads = validate_and_stage_rows(source_file, rows, mapping)
            except Exception as exc:  # noqa: BLE001
                form.add_error(None, str(exc))
            else:
                with transaction.atomic():
                    source_file.column_mapping = mapping
                    source_file.save(update_fields=["column_mapping"])
                    batch.records.filter(source_file=source_file).delete()
                    MigrationRecord.objects.bulk_create(
                        [
                            MigrationRecord(
                                batch=batch, source_file=source_file,
                                row_number=p["row_number"], source_values=p["source_values"],
                                mapped_values=p["mapped_values"], validation_status=p["validation_status"],
                                validation_errors=p["validation_errors"],
                                is_duplicate_in_file=p["is_duplicate_in_file"],
                                review_status=(
                                    MigrationRecord.ReviewStatus.NEEDS_REVIEW
                                    if p["validation_status"] == MigrationRecord.ValidationStatus.INVALID
                                    else MigrationRecord.ReviewStatus.NEEDS_REVIEW
                                ),
                            )
                            for p in staged_payloads
                        ]
                    )
                    if batch.status in {MigrationBatch.Status.DRAFT, MigrationBatch.Status.UPLOADED}:
                        batch.status = MigrationBatch.Status.UNDER_REVIEW
                        batch.save(update_fields=["status"])
                    _record_migration_action(
                        batch, request.user, "records_staged", source_file=source_file,
                        details=f"Staged {len(staged_payloads)} row(s) for review (no patient records created).",
                    )
                # run matching to suggest statuses/candidates
                run_matching_for_batch(batch)
                _record_migration_action(batch, request.user, "matching_completed", details="Automatic matching suggestions generated for staged records.")
                return redirect("record_migration:digital_review", batch_id=batch.pk)

    return render(
        request, "record_migration/column_mapping.html",
        {"batch": batch, "source_file": source_file, "form": form, "headers": headers, "saved": saved},
    )


@login_required
@require_GET
def digital_review(request, batch_id):
    batch = get_object_or_404(MigrationBatch, pk=batch_id)
    if not can_access_batch(request.user, batch):
        return HttpResponseForbidden("You are not authorised to access this migration batch.")
    records = MigrationRecord.objects.filter(batch=batch).select_related("source_file", "matched_patient", "imported_patient").order_by("source_file_id", "row_number")
    summary = summarize_staged(records)
    # Part 3 review counts
    review_counts = {
        "new_patient": records.filter(review_status=MigrationRecord.ReviewStatus.NEW_PATIENT).count(),
        "existing_match": records.filter(review_status=MigrationRecord.ReviewStatus.EXISTING_PATIENT_MATCH).count(),
        "possible_duplicate": records.filter(review_status=MigrationRecord.ReviewStatus.POSSIBLE_DUPLICATE).count(),
        "needs_review": records.filter(review_status=MigrationRecord.ReviewStatus.NEEDS_REVIEW).count(),
        "ready_for_approval": records.filter(review_status=MigrationRecord.ReviewStatus.READY_FOR_APPROVAL).count(),
        "rejected": records.filter(review_status=MigrationRecord.ReviewStatus.REJECTED).count(),
        "imported": records.filter(review_status=MigrationRecord.ReviewStatus.IMPORTED).count(),
    }
    status_filter = request.GET.get("status", "")
    review_filter = request.GET.get("review", "")
    if status_filter:
        records = records.filter(validation_status=status_filter)
    if review_filter:
        records = records.filter(review_status=review_filter)
    return render(
        request,
        "record_migration/digital_review.html",
        {
            "batch": batch, "records": records[:300], "summary": summary,
            "review_counts": review_counts,
            "status_filter": status_filter, "review_filter": review_filter,
            "status_choices": MigrationRecord.ValidationStatus.choices,
            "review_choices": MigrationRecord.ReviewStatus.choices,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def staged_record_detail(request, batch_id, record_id):
    batch = get_object_or_404(MigrationBatch, pk=batch_id)
    if not can_access_batch(request.user, batch):
        return HttpResponseForbidden("You are not authorised to access this migration batch.")
    record = get_object_or_404(
        MigrationRecord.objects.select_related("source_file", "matched_patient", "approved_by", "decided_by", "imported_patient"),
        pk=record_id, batch=batch,
    )
    # refresh matching suggestions for display (does not override human decisions/status except suggestions)
    from .services import detect_patient_matches
    candidates, suggested_status, conflicts_now, _ = detect_patient_matches(record.mapped_values or {}, record=record, batch=batch)
    # show persisted candidates primarily, fall back to fresh
    display_candidates = record.match_candidates or candidates
    # resolve candidate patient objects for display (only identifying info)
    candidate_patients = []
    for c in display_candidates:
        p = Patient.objects.filter(pk=c.get("patient_id")).first()
        if p:
            candidate_patients.append({
                "patient": p,
                "reason": c.get("reason", ""),
                "strength": c.get("strength", ""),
            })

    decision_form = RecordDecisionForm(
        request.POST or None,
        initial={
            "decision": record.decision if record.decision != MigrationRecord.Decision.NONE else "",
            "matched_patient_id": record.matched_patient_id or "",
            "reason": record.decision_reason,
        },
    )
    action_error = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_decision":
            if record.is_imported:
                action_error = "Imported records cannot be changed."
            elif decision_form.is_valid():
                decision = decision_form.cleaned_data["decision"]
                reason = decision_form.cleaned_data["reason"]
                matched_id = decision_form.cleaned_data.get("matched_patient_id")
                with transaction.atomic():
                    rec = MigrationRecord.objects.select_for_update().get(pk=record.pk)
                    rec.decision = decision
                    rec.decision_reason = reason
                    rec.decided_by = request.user
                    rec.decided_at = timezone.now()
                    rec.approved_by = None
                    rec.approved_at = None
                    # reset review status based on decision (conflicts/duplicates may override)
                    if decision == "REJECT":
                        rec.review_status = MigrationRecord.ReviewStatus.REJECTED
                        rec.matched_patient = None
                    elif decision == "FLAG":
                        rec.review_status = MigrationRecord.ReviewStatus.NEEDS_REVIEW
                    elif decision == "LINK_EXISTING":
                        mp = Patient.objects.filter(pk=matched_id).first()
                        rec.matched_patient = mp
                        # re-check conflicts against selected patient
                        from .services import compare_patient_conflicts
                        rec.conflicts = compare_patient_conflicts(mp, rec.mapped_values or {}) if mp else []
                        if rec.conflicts or rec.is_duplicate_in_file:
                            rec.review_status = MigrationRecord.ReviewStatus.POSSIBLE_DUPLICATE if not rec.conflicts else MigrationRecord.ReviewStatus.NEEDS_REVIEW
                            if rec.conflicts:
                                rec.review_status = MigrationRecord.ReviewStatus.NEEDS_REVIEW
                            else:
                                rec.review_status = MigrationRecord.ReviewStatus.EXISTING_PATIENT_MATCH
                        else:
                            rec.review_status = MigrationRecord.ReviewStatus.EXISTING_PATIENT_MATCH
                    elif decision == "CREATE_NEW":
                        rec.matched_patient = None
                        if rec.is_duplicate_in_file or any("already imported" in c.lower() for c in (rec.conflicts or [])):
                            rec.review_status = MigrationRecord.ReviewStatus.POSSIBLE_DUPLICATE
                        else:
                            # keep possible duplicate if matching found strong candidates? conservative
                            rec.review_status = MigrationRecord.ReviewStatus.NEW_PATIENT
                    rec.save()
                    _record_migration_action(
                        batch, request.user, "match_decision_saved", record=rec,
                        details=f"Decision '{rec.get_decision_display()}' saved for row {rec.row_number}. Reason: {reason or '—'}",
                    )
                _refresh_batch_status(batch)
                messages.success(request, "Review decision saved.")
                return redirect("record_migration:staged_record_detail", batch_id=batch.pk, record_id=record.pk)
        elif action == "approve":
            if record.is_imported:
                action_error = "Imported records cannot be approved again."
            else:
                # allow self-approve only if no other admin/doctor exists? enforce separate reviewer when uploader known and different users exist
                can, reason = can_approve_record(record, request.user)
                # relax self-approval only when uploader is the only migration-capable user impossible to prove; keep strict
                if not can:
                    action_error = reason
                else:
                    with transaction.atomic():
                        rec = MigrationRecord.objects.select_for_update().get(pk=record.pk)
                        can2, reason2 = can_approve_record(rec, request.user)
                        if not can2:
                            action_error = reason2
                        else:
                            rec.approved_by = request.user
                            rec.approved_at = timezone.now()
                            rec.review_status = MigrationRecord.ReviewStatus.READY_FOR_APPROVAL
                            rec.save(update_fields=["approved_by", "approved_at", "review_status"])
                            _record_migration_action(
                                batch, request.user, "record_approved", record=rec,
                                details=f"Row {rec.row_number} approved by {request.user} for import.",
                            )
                    if not action_error:
                        _refresh_batch_status(batch)
                        messages.success(request, "Record approved for import.")
                        return redirect("record_migration:staged_record_detail", batch_id=batch.pk, record_id=record.pk)
        elif action == "import":
            ok, msg, patient = import_staged_record(record.pk, request.user)
            if ok:
                _refresh_batch_status(batch)
                messages.success(request, msg)
            else:
                _refresh_batch_status(batch)
                action_error = msg
            if ok:
                return redirect("record_migration:staged_record_detail", batch_id=batch.pk, record_id=record.pk)
        else:
            action_error = "Unknown action."

    # re-fetch after possible refresh context
    record = get_object_or_404(
        MigrationRecord.objects.select_related("source_file", "matched_patient", "approved_by", "decided_by", "imported_patient"),
        pk=record_id, batch=batch,
    )
    can_approve, approve_reason = can_approve_record(record, request.user)
    return render(
        request,
        "record_migration/staged_record_detail.html",
        {
            "batch": batch, "record": record, "candidate_patients": candidate_patients,
            "suggested_status": suggested_status, "conflicts_now": conflicts_now,
            "decision_form": decision_form, "action_error": action_error,
            "can_approve": can_approve, "approve_reason": approve_reason,
        },
    )


@login_required
@require_POST
def run_matching(request, batch_id):
    batch = get_object_or_404(MigrationBatch, pk=batch_id)
    if not can_access_batch(request.user, batch):
        return HttpResponseForbidden("You are not authorised to modify this migration batch.")
    updated = run_matching_for_batch(batch)
    _record_migration_action(batch, request.user, "matching_completed", details=f"Matching refreshed for {updated} record(s).")
    messages.success(request, f"Matching suggestions refreshed for {updated} record(s).")
    return redirect("record_migration:digital_review", batch_id=batch.pk)


@login_required
@require_POST
def remove_spreadsheet(request, batch_id, file_id):
    batch = get_object_or_404(MigrationBatch, pk=batch_id)
    if not can_access_batch(request.user, batch):
        return HttpResponseForbidden("You are not authorised to modify this migration batch.")
    if batch.migration_type != MigrationBatch.MigrationType.DIGITAL or batch.status != MigrationBatch.Status.DRAFT:
        return HttpResponseForbidden("Files can only be removed from draft digital batches.")
    source_file = get_object_or_404(MigrationFile, pk=file_id, batch=batch)
    name = source_file.original_filename
    with transaction.atomic():
        source_file.file.delete(save=False)
        source_file.delete()
        batch.records.all().delete()
        batch.status = MigrationBatch.Status.DRAFT
        batch.save(update_fields=["status"])
        _record_migration_action(batch, request.user, "spreadsheet_removed", details=f"Spreadsheet removed: {name}.")
    return redirect("record_migration:upload_spreadsheet", batch_id=batch.pk)


@login_required
@require_GET
def patient_documents(request, patient_id):
    if request.user.role == User.Role.ADMIN:
        patient_access = True
    elif request.user.role == User.Role.DOCTOR:
        patient_access = doctor_patient_queryset(request.user).filter(pk=patient_id).exists()
    else:
        return HttpResponseForbidden("You are not authorised to access clinical documents.")
    if not patient_access:
        raise Http404

    patient_documents = MigrationDocument.objects.filter(patient_id=patient_id).select_related("batch").order_by("-created_at")
    return render(request, "record_migration/patient_documents.html", {"documents": patient_documents, "patient_id": patient_id})


@login_required
@require_GET
def download_document(request, document_id):
    if request.user.role not in {User.Role.ADMIN, User.Role.DOCTOR}:
        return HttpResponseForbidden("You are not authorised to access clinical documents.")
    document = get_object_or_404(MigrationDocument.objects.select_related("batch", "patient"), pk=document_id)
    if request.user.role == User.Role.DOCTOR and not doctor_patient_queryset(request.user).filter(pk=document.patient_id).exists():
        raise Http404

    extension = PurePath(document.file.name).suffix.lower()
    filename = f"patient-record-{document.pk}{extension}"
    response = FileResponse(document.file.open("rb"), as_attachment=True, filename=filename)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    response["Content-Type"] = document.mime_type
    return response


@login_required
@require_GET
def history(request):
    if not can_view_migrations(request.user):
        return HttpResponseForbidden("You are not authorised to access migration history.")
    batches_qs = accessible_batches(request.user).select_related("created_by").annotate(
        document_count=Count("documents", distinct=True),
        file_count=Count("files", distinct=True),
        staged_count=Count("records", distinct=True),
        imported_count=Count("records", filter=Q(records__is_imported=True), distinct=True),
        error_count=Count(
            "records",
            filter=Q(records__validation_status=MigrationRecord.ValidationStatus.INVALID) | Q(records__import_error__gt=""),
            distinct=True,
        ),
    )
    if request.user.role == User.Role.DOCTOR:
        batches_qs = batches_qs.filter(created_by=request.user)

    # Filters
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    migration_type = (request.GET.get("migration_type") or "").strip()
    batch_status = (request.GET.get("status") or "").strip()
    staff_id = (request.GET.get("staff") or "").strip()
    outcome = (request.GET.get("outcome") or "").strip()

    if date_from:
        try:
            batches_qs = batches_qs.filter(created_at__date__gte=timezone.datetime.strptime(date_from, "%Y-%m-%d").date())
        except ValueError:
            pass
    if date_to:
        try:
            batches_qs = batches_qs.filter(created_at__date__lte=timezone.datetime.strptime(date_to, "%Y-%m-%d").date())
        except ValueError:
            pass
    if migration_type in {c[0] for c in MigrationBatch.MigrationType.choices}:
        batches_qs = batches_qs.filter(migration_type=migration_type)
    if batch_status in {c[0] for c in MigrationBatch.Status.choices}:
        batches_qs = batches_qs.filter(status=batch_status)
    if staff_id.isdigit():
        batches_qs = batches_qs.filter(created_by_id=int(staff_id))
    if outcome == "imported":
        batches_qs = batches_qs.filter(imported_count__gt=0)
    elif outcome == "rejected":
        batches_qs = batches_qs.filter(records__review_status=MigrationRecord.ReviewStatus.REJECTED).distinct()
    elif outcome == "errors":
        batches_qs = batches_qs.filter(error_count__gt=0)
    elif outcome == "awaiting":
        batches_qs = batches_qs.filter(records__is_imported=False).exclude(records__review_status=MigrationRecord.ReviewStatus.REJECTED).distinct()

    batches_qs = batches_qs.order_by("-created_at")
    paginator = Paginator(batches_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    activities = MigrationAuditLog.objects.filter(batch__in=accessible_batches(request.user)).select_related(
        "actor", "batch", "document", "source_file", "record"
    )
    if request.user.role == User.Role.DOCTOR:
        activities = activities.filter(batch__created_by=request.user)
    if date_from:
        try:
            activities = activities.filter(created_at__date__gte=timezone.datetime.strptime(date_from, "%Y-%m-%d").date())
        except ValueError:
            pass
    if date_to:
        try:
            activities = activities.filter(created_at__date__lte=timezone.datetime.strptime(date_to, "%Y-%m-%d").date())
        except ValueError:
            pass
    if migration_type in {c[0] for c in MigrationBatch.MigrationType.choices}:
        activities = activities.filter(batch__migration_type=migration_type)
    if batch_status in {c[0] for c in MigrationBatch.Status.choices}:
        activities = activities.filter(batch__status=batch_status)
    if staff_id.isdigit():
        activities = activities.filter(actor_id=int(staff_id))
    if outcome == "imported":
        activities = activities.filter(action="record_imported")
    elif outcome == "rejected":
        activities = activities.filter(action="match_decision_saved", details__icontains="Reject")
    elif outcome == "errors":
        activities = activities.filter(Q(details__icontains="error") | Q(action__icontains="error"))

    activities_page = Paginator(activities.order_by("-created_at"), 50).get_page(request.GET.get("apage"))

    staff_choices = User.objects.filter(
        pk__in=MigrationAuditLog.objects.filter(batch__in=accessible_batches(request.user)).values_list("actor_id", flat=True)
    ).order_by("first_name", "last_name", "username")
    if request.user.role == User.Role.DOCTOR:
        staff_choices = staff_choices.filter(pk=request.user.pk)

    return render(
        request,
        "record_migration/history.html",
        {
            "batches": page_obj,
            "page_obj": page_obj,
            "activities": activities_page,
            "activities_page": activities_page,
            "today": timezone.localdate(),
            "filters": {
                "date_from": date_from, "date_to": date_to, "migration_type": migration_type,
                "status": batch_status, "staff": staff_id, "outcome": outcome,
            },
            "migration_types": MigrationBatch.MigrationType.choices,
            "statuses": MigrationBatch.Status.choices,
            "staff_choices": staff_choices,
        },
    )


@login_required
@require_GET
def batch_report(request, batch_id):
    batch = get_object_or_404(MigrationBatch.objects.select_related("created_by"), pk=batch_id)
    if not can_access_batch(request.user, batch):
        return HttpResponseForbidden("You are not authorised to access this migration batch.")
    report = batch_report_data(batch)
    errors = batch_error_rows(batch)
    return render(
        request,
        "record_migration/batch_report.html",
        {"batch": batch, "report": report, "errors": errors[:200], "error_total": len(errors)},
    )


@login_required
@require_GET
def download_error_report(request, batch_id):
    batch = get_object_or_404(MigrationBatch, pk=batch_id)
    if not can_access_batch(request.user, batch):
        return HttpResponseForbidden("You are not authorised to access this migration batch.")
    errors = batch_error_rows(batch)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="migration-batch-{batch.pk}-errors.csv"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    writer = csv.writer(response)
    writer.writerow(["Batch ID", "Batch name", "Spreadsheet row number", "Source file", "Error type", "Error description", "Current resolution status"])
    for row in errors:
        writer.writerow([
            batch.pk,
            batch.name,
            row["row_number"] or "",
            row["source_file"] or "",
            row["error_type"],
            row["description"],
            row["resolution_status"],
        ])
    _record_migration_action(batch, request.user, "error_report_downloaded", details="Error report CSV downloaded.")
    return response
