from datetime import date
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import User
from appointments.models import QueueEntry
from patients.models import Patient
from record_migration.models import MigrationAuditLog, MigrationBatch, MigrationDocument, MigrationRecord, MigrationFile


def make_image_file(name="scan.png", fmt="PNG", size=(10, 10), color=(255, 255, 255)):
    buf = BytesIO()
    image = Image.new("RGB", size, color)
    image.save(buf, format=fmt)
    content = buf.getvalue()
    content_type = "image/png" if fmt == "PNG" else "image/jpeg"
    return SimpleUploadedFile(name, content, content_type=content_type)


def make_pdf_file(name="scan.pdf"):
    content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    return SimpleUploadedFile(name, content, content_type="application/pdf")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RecordMigrationPart1Tests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="adminmig",
            password="StrongPass123!",
            role=User.Role.ADMIN,
            is_approved=True,
            is_active=True,
            first_name="Admin",
            last_name="Migration",
        )
        self.doctor = User.objects.create_user(
            username="doctormig",
            password="StrongPass123!",
            role=User.Role.DOCTOR,
            is_approved=True,
            is_active=True,
            first_name="Doctor",
            last_name="Migration",
        )
        self.other_doctor = User.objects.create_user(
            username="otherdocmig",
            password="StrongPass123!",
            role=User.Role.DOCTOR,
            is_approved=True,
            is_active=True,
        )
        self.receptionist = User.objects.create_user(
            username="receptionmig",
            password="StrongPass123!",
            role=User.Role.RECEPTIONIST,
            is_approved=True,
            is_active=True,
        )
        self.patient = Patient.objects.create(
            full_name="Migrated Patient",
            date_of_birth="1985-04-10",
            sex=Patient.Sex.FEMALE,
            phone_number="+263771110000",
            allergies="Penicillin",
            notes="Private clinical note",
            registered_by=self.receptionist,
        )
        QueueEntry.objects.create(
            patient=self.patient,
            assigned_doctor=self.doctor,
            queue_number="Q-MIG-1",
        )

    def create_batch(self, user=None, **overrides):
        owner = user or self.doctor
        data = {
            "name": "Paper Batch 1",
            "migration_type": MigrationBatch.MigrationType.PAPER,
            "source_hospital": "Old Clinic",
            "source_department": "Records",
            "source_system": "",
            "description": "Legacy files",
            "status": MigrationBatch.Status.DRAFT,
            "created_by": owner,
        }
        data.update(overrides)
        return MigrationBatch.objects.create(**data)

    def test_dashboard_requires_authorised_staff(self):
        self.client.force_login(self.receptionist)
        response = self.client.get(reverse("record_migration:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_admin_and_doctor_can_access_dashboard(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("record_migration:dashboard")).status_code, 200)
        self.client.force_login(self.doctor)
        self.assertEqual(self.client.get(reverse("record_migration:dashboard")).status_code, 200)

    def test_create_paper_batch_records_audit(self):
        self.client.force_login(self.doctor)
        response = self.client.post(
            reverse("record_migration:create_batch"),
            {
                "name": "Ward A Scans",
                "migration_type": MigrationBatch.MigrationType.PAPER,
                "source_hospital": "Central Hospital",
                "source_department": "Ward A",
                "source_system": "",
                "description": "Old paper files",
            },
        )
        batch = MigrationBatch.objects.get(name="Ward A Scans")
        self.assertRedirects(response, reverse("record_migration:upload_document", args=[batch.pk]))
        self.assertEqual(batch.created_by, self.doctor)
        self.assertTrue(
            MigrationAuditLog.objects.filter(batch=batch, action="batch_created", actor=self.doctor).exists()
        )

    def test_receptionist_cannot_create_or_upload(self):
        batch = self.create_batch()
        self.client.force_login(self.receptionist)
        self.assertEqual(self.client.get(reverse("record_migration:create_batch")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("record_migration:upload_document", args=[batch.pk])).status_code,
            403,
        )

    @override_settings(IS_VERCEL=False)
    def test_upload_pdf_attaches_to_patient_and_audits(self):
        batch = self.create_batch(user=self.doctor)
        self.client.force_login(self.doctor)
        response = self.client.post(
            reverse("record_migration:upload_document", args=[batch.pk]),
            {
                "patient": self.patient.pk,
                "file": make_pdf_file(),
                "document_date": "2019-06-01",
                "source": "Archive Room",
                "description": "Discharge summary",
            },
        )
        self.assertRedirects(response, reverse("record_migration:dashboard"))
        batch.refresh_from_db()
        doc = MigrationDocument.objects.get(batch=batch, patient=self.patient)
        self.assertEqual(doc.original_filename, "scan.pdf")
        self.assertEqual(doc.mime_type, "application/pdf")
        self.assertEqual(doc.source, "Archive Room")
        self.assertEqual(batch.status, MigrationBatch.Status.UPLOADED)
        self.assertTrue(
            MigrationAuditLog.objects.filter(
                batch=batch, document=doc, action="document_uploaded", actor=self.doctor
            ).exists()
        )

    @override_settings(IS_VERCEL=False)
    def test_upload_png_and_jpg_are_accepted(self):
        batch = self.create_batch(user=self.admin)
        self.client.force_login(self.admin)
        for name, fmt, ctype in [("scan.png", "PNG", "image/png"), ("scan.jpg", "JPEG", "image/jpeg")]:
            resp = self.client.post(
                reverse("record_migration:upload_document", args=[batch.pk]),
                {
                    "patient": self.patient.pk,
                    "file": make_image_file(name=name, fmt=fmt),
                    "document_date": "2020-01-02",
                    "source": "Registry",
                    "description": "",
                },
            )
            self.assertRedirects(resp, reverse("record_migration:dashboard"))
        self.assertEqual(MigrationDocument.objects.filter(batch=batch).count(), 2)

    @override_settings(IS_VERCEL=False)
    def test_invalid_extension_and_content_rejected(self):
        batch = self.create_batch(user=self.doctor)
        self.client.force_login(self.doctor)
        bad_ext = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        response = self.client.post(
            reverse("record_migration:upload_document", args=[batch.pk]),
            {
                "patient": self.patient.pk,
                "file": bad_ext,
                "document_date": "2019-06-01",
                "source": "Archive",
                "description": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MigrationDocument.objects.filter(batch=batch).exists())

        fake_pdf = SimpleUploadedFile("fake.pdf", b"not a pdf", content_type="application/pdf")
        response = self.client.post(
            reverse("record_migration:upload_document", args=[batch.pk]),
            {
                "patient": self.patient.pk,
                "file": fake_pdf,
                "document_date": "2019-06-01",
                "source": "Archive",
                "description": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MigrationDocument.objects.filter(batch=batch).exists())

    @override_settings(IS_VERCEL=False)
    def test_oversized_file_rejected(self):
        batch = self.create_batch(user=self.doctor)
        self.client.force_login(self.doctor)
        big = SimpleUploadedFile(
            "big.pdf",
            b"%PDF-1.4\n" + (b"a" * (10 * 1024 * 1024 + 1)) + b"\n%%EOF",
            content_type="application/pdf",
        )
        response = self.client.post(
            reverse("record_migration:upload_document", args=[batch.pk]),
            {
                "patient": self.patient.pk,
                "file": big,
                "document_date": "2019-06-01",
                "source": "Archive",
                "description": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MigrationDocument.objects.filter(batch=batch).exists())

    @override_settings(IS_VERCEL=False)
    def test_doctor_cannot_access_other_doctors_batch_or_unrelated_patient_document(self):
        batch = self.create_batch(user=self.doctor)
        self.client.force_login(self.doctor)
        self.client.post(
            reverse("record_migration:upload_document", args=[batch.pk]),
            {
                "patient": self.patient.pk,
                "file": make_pdf_file(),
                "document_date": "2019-06-01",
                "source": "Archive",
                "description": "",
            },
        )
        doc = MigrationDocument.objects.get(batch=batch)

        self.client.force_login(self.other_doctor)
        self.assertEqual(self.client.get(reverse("record_migration:upload_document", args=[batch.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("record_migration:download_document", args=[doc.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("record_migration:patient_documents", args=[self.patient.pk])).status_code, 404)

    @override_settings(IS_VERCEL=False)
    def test_receptionist_cannot_download_or_list_clinical_documents(self):
        batch = self.create_batch(user=self.doctor)
        self.client.force_login(self.doctor)
        self.client.post(
            reverse("record_migration:upload_document", args=[batch.pk]),
            {
                "patient": self.patient.pk,
                "file": make_pdf_file(),
                "document_date": "2019-06-01",
                "source": "Archive",
                "description": "",
            },
        )
        doc = MigrationDocument.objects.get(batch=batch)
        self.client.force_login(self.receptionist)
        self.assertEqual(self.client.get(reverse("record_migration:download_document", args=[doc.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("record_migration:patient_documents", args=[self.patient.pk])).status_code, 403)

    @override_settings(IS_VERCEL=False)
    def test_authorised_download_is_private_attachment(self):
        batch = self.create_batch(user=self.admin)
        self.client.force_login(self.admin)
        self.client.post(
            reverse("record_migration:upload_document", args=[batch.pk]),
            {
                "patient": self.patient.pk,
                "file": make_pdf_file(),
                "document_date": "2019-06-01",
                "source": "Archive",
                "description": "",
            },
        )
        doc = MigrationDocument.objects.get(batch=batch)
        response = self.client.get(reverse("record_migration:download_document", args=[doc.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.get("Content-Disposition", ""))
        self.assertEqual(response.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.get("Cache-Control"), "private, no-store")
        self.assertEqual(response.get("Content-Type"), "application/pdf")

    def test_history_requires_authorised_staff(self):
        self.client.force_login(self.receptionist)
        self.assertEqual(self.client.get(reverse("record_migration:history")).status_code, 403)
        self.client.force_login(self.doctor)
        self.assertEqual(self.client.get(reverse("record_migration:history")).status_code, 200)


def make_csv_file(name="patients.csv", rows=None, header=None):
    import csv
    from io import StringIO

    output = StringIO()
    header = header or ["Full Name", "Date of Birth", "Sex", "Phone"]
    writer = csv.writer(output)
    writer.writerow(header)
    for row in (rows or [["Jane Doe", "1990-01-02", "Female", "+263700000001"]]):
        writer.writerow(row)
    content = output.getvalue().encode("utf-8")
    return SimpleUploadedFile(name, content, content_type="text/csv")


def make_xlsx_file(name="patients.xlsx", rows=None, header=None):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    header = header or ["Full Name", "Date of Birth", "Sex", "Phone"]
    ws.append(header)
    for row in (rows or [["Jane Doe", "1990-01-02", "Female", "+263700000001"]]):
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return SimpleUploadedFile(
        name,
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RecordMigrationPart2Tests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="adminmig2", password="StrongPass123!", role=User.Role.ADMIN,
            is_approved=True, is_active=True,
        )
        self.doctor = User.objects.create_user(
            username="doctormig2", password="StrongPass123!", role=User.Role.DOCTOR,
            is_approved=True, is_active=True,
        )
        self.other_doctor = User.objects.create_user(
            username="otherdocmig2", password="StrongPass123!", role=User.Role.DOCTOR,
            is_approved=True, is_active=True,
        )
        self.receptionist = User.objects.create_user(
            username="receptionmig2", password="StrongPass123!", role=User.Role.RECEPTIONIST,
            is_approved=True, is_active=True,
        )

    def create_digital_batch(self, user=None, status=None):
        owner = user or self.doctor
        return MigrationBatch.objects.create(
            name="Digital Batch",
            migration_type=MigrationBatch.MigrationType.DIGITAL,
            source_hospital="Old Hospital",
            description="Spreadsheet import",
            status=status or MigrationBatch.Status.DRAFT,
            created_by=owner,
        )

    def default_mapping(self, source_file, include_required=True):
        """Return POST data mapping detected headers to CareLink fields."""
        headers = source_file.column_headers or []
        data = {}
        def pick(options):
            for h in headers:
                if h in options:
                    return h
            return ""
        if include_required:
            data["map_full_name"] = pick(["Full Name", "Name", "full_name"])
            data["map_date_of_birth"] = pick(["Date of Birth", "DOB", "date_of_birth"])
            data["map_sex"] = pick(["Sex", "Gender", "sex"])
        data["map_phone_number"] = pick(["Phone", "Phone Number", "phone_number"])
        return data

    def upload_and_get_file(self, batch):
        resp = self.client.post(
            reverse("record_migration:upload_spreadsheet", args=[batch.pk]),
            {"file": make_csv_file()},
        )
        self.assertEqual(resp.status_code, 302)
        return batch.files.get()

    # --- permissions / access ---
    def test_digital_upload_requires_authorised_staff(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.receptionist)
        self.assertEqual(self.client.get(reverse("record_migration:upload_spreadsheet", args=[batch.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("record_migration:upload_spreadsheet", args=[batch.pk]), {"file": make_csv_file()}).status_code, 403)

    def test_doctor_cannot_access_other_doctors_digital_batch(self):
        batch = self.create_digital_batch(user=self.doctor)
        self.client.force_login(self.other_doctor)
        self.assertEqual(self.client.get(reverse("record_migration:upload_spreadsheet", args=[batch.pk])).status_code, 403)

    def test_digital_upload_forbidden_on_paper_batch(self):
        paper = MigrationBatch.objects.create(
            name="Paper", migration_type=MigrationBatch.MigrationType.PAPER,
            status=MigrationBatch.Status.DRAFT, created_by=self.doctor,
        )
        self.client.force_login(self.doctor)
        self.assertEqual(self.client.get(reverse("record_migration:upload_spreadsheet", args=[paper.pk])).status_code, 403)

    # --- uploads ---
    @override_settings(IS_VERCEL=False)
    def test_csv_upload_creates_file_and_audit(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        resp = self.client.post(
            reverse("record_migration:upload_spreadsheet", args=[batch.pk]),
            {"file": make_csv_file()},
        )
        self.assertEqual(resp.status_code, 302)
        batch.refresh_from_db()
        sf = batch.files.get()
        self.assertEqual(sf.file_type, "CSV")
        self.assertEqual(sf.row_count, 1)
        self.assertIn("Full Name", sf.column_headers)
        self.assertEqual(batch.status, MigrationBatch.Status.UPLOADED)
        self.assertTrue(MigrationAuditLog.objects.filter(batch=batch, source_file=sf, action="spreadsheet_uploaded").exists())

    @override_settings(IS_VERCEL=False)
    def test_xlsx_upload_creates_file(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        resp = self.client.post(
            reverse("record_migration:upload_spreadsheet", args=[batch.pk]),
            {"file": make_xlsx_file()},
        )
        self.assertEqual(resp.status_code, 302)
        sf = batch.files.get()
        self.assertEqual(sf.file_type, "XLSX")
        self.assertEqual(sf.row_count, 1)

    @override_settings(IS_VERCEL=False)
    def test_unsupported_file_type_rejected(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        bad = SimpleUploadedFile("data.txt", b"hello", content_type="text/plain")
        resp = self.client.post(reverse("record_migration:upload_spreadsheet", args=[batch.pk]), {"file": bad})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(batch.files.exists())

    @override_settings(IS_VERCEL=False)
    def test_malformed_csv_rejected(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        bad = SimpleUploadedFile("bad.csv", b"\xff\xfe\x00\x00bad", content_type="text/csv")
        resp = self.client.post(reverse("record_migration:upload_spreadsheet", args=[batch.pk]), {"file": bad})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(batch.files.exists())

    @override_settings(IS_VERCEL=False)
    def test_malformed_xlsx_rejected(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        bad = SimpleUploadedFile("bad.xlsx", b"PK\x03\x04garbage-not-xlsx", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp = self.client.post(reverse("record_migration:upload_spreadsheet", args=[batch.pk]), {"file": bad})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(batch.files.exists())

    @override_settings(IS_VERCEL=False)
    def test_spreadsheet_size_limit_rejected(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        big = SimpleUploadedFile("big.csv", b"col\n" + b"a\n" * (5 * 1024 * 1024), content_type="text/csv")
        resp = self.client.post(reverse("record_migration:upload_spreadsheet", args=[batch.pk]), {"file": big})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(batch.files.exists())

    @override_settings(IS_VERCEL=False)
    def test_row_count_limit_rejected(self):
        from record_migration.services import MAX_SPREADSHEET_ROWS
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        rows = [["Name", "1990-01-01", "F", "1"] for _ in range(MAX_SPREADSHEET_ROWS + 1)]
        resp = self.client.post(
            reverse("record_migration:upload_spreadsheet", args=[batch.pk]),
            {"file": make_csv_file(rows=rows)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(batch.files.exists())
        self.assertContains(resp, "at most")

    # --- preview ---
    @override_settings(IS_VERCEL=False)
    def test_spreadsheet_preview_shows_headers_rows_and_counts(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        sf = self.upload_and_get_file(batch)
        resp = self.client.get(reverse("record_migration:spreadsheet_preview", args=[batch.pk, sf.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Full Name")
        self.assertContains(resp, "Jane Doe")
        self.assertContains(resp, "Total data records")
        self.assertEqual(resp.context["total_rows"], 1)

    # --- mapping & staging ---
    @override_settings(IS_VERCEL=False)
    def test_save_column_mapping_audits(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        sf = self.upload_and_get_file(batch)
        data = self.default_mapping(sf)
        data["save_mapping"] = "1"
        resp = self.client.post(reverse("record_migration:column_mapping", args=[batch.pk, sf.pk]), data)
        self.assertEqual(resp.status_code, 200)
        sf.refresh_from_db()
        self.assertEqual(sf.column_mapping.get("full_name"), "Full Name")
        self.assertTrue(MigrationAuditLog.objects.filter(batch=batch, action="column_mapping_saved").exists())

    @override_settings(IS_VERCEL=False)
    def test_validate_and_stage_creates_records_without_creating_patients(self):
        from patients.models import Patient
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        sf = self.upload_and_get_file(batch)
        before = Patient.objects.count()
        data = self.default_mapping(sf)
        data["validate_stage"] = "1"
        resp = self.client.post(reverse("record_migration:column_mapping", args=[batch.pk, sf.pk]), data)
        self.assertRedirects(resp, reverse("record_migration:digital_review", args=[batch.pk]))
        self.assertEqual(Patient.objects.count(), before)
        self.assertEqual(batch.records.count(), 1)
        rec = batch.records.get()
        self.assertEqual(rec.validation_status, "VALID")
        self.assertEqual(rec.row_number, 2)
        self.assertEqual(rec.source_values.get("Full Name"), "Jane Doe")
        self.assertEqual(rec.mapped_values.get("full_name"), "Jane Doe")
        batch.refresh_from_db()
        self.assertEqual(batch.status, MigrationBatch.Status.UNDER_REVIEW)
        self.assertTrue(MigrationAuditLog.objects.filter(batch=batch, action="records_staged").exists())

    @override_settings(IS_VERCEL=False)
    def test_validation_missing_required_fields_and_invalid_values(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        # missing DOB, invalid sex, bad date
        f = make_csv_file(rows=[["", "not-a-date", "Unknown", "123"]], header=["Full Name", "Date of Birth", "Sex", "Phone"])
        self.client.post(reverse("record_migration:upload_spreadsheet", args=[batch.pk]), {"file": f})
        sf = batch.files.get()
        data = {"map_full_name": "Full Name", "map_date_of_birth": "Date of Birth", "map_sex": "Sex", "map_phone_number": "Phone", "validate_stage": "1"}
        self.client.post(reverse("record_migration:column_mapping", args=[batch.pk, sf.pk]), data)
        rec = batch.records.get()
        self.assertEqual(rec.validation_status, "INVALID")
        msgs = " ".join(rec.validation_errors)
        self.assertIn("required", msgs.lower())
        self.assertIn("Invalid", msgs)

    @override_settings(IS_VERCEL=False)
    def test_duplicate_rows_in_spreadsheet_detected(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        dup_rows = [
            ["Jane Doe", "1990-01-02", "F", "1"],
            ["Jane Doe", "1990-01-02", "F", "1"],
        ]
        self.client.post(reverse("record_migration:upload_spreadsheet", args=[batch.pk]), {"file": make_csv_file(rows=dup_rows)})
        sf = batch.files.get()
        data = self.default_mapping(sf)
        data["validate_stage"] = "1"
        self.client.post(reverse("record_migration:column_mapping", args=[batch.pk, sf.pk]), data)
        recs = list(batch.records.order_by("row_number"))
        self.assertEqual(recs[0].validation_status, "VALID")
        self.assertEqual(recs[1].validation_status, "INVALID")
        self.assertTrue(recs[1].is_duplicate_in_file)

    @override_settings(IS_VERCEL=False)
    def test_empty_row_marked_invalid(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        rows = [["Jane Doe", "1990-01-02", "F", "1"], ["", "", "", ""]]
        self.client.post(reverse("record_migration:upload_spreadsheet", args=[batch.pk]), {"file": make_csv_file(rows=rows)})
        sf = batch.files.get()
        data = self.default_mapping(sf)
        data["validate_stage"] = "1"
        self.client.post(reverse("record_migration:column_mapping", args=[batch.pk, sf.pk]), data)
        empty = batch.records.get(row_number=3)
        self.assertEqual(empty.validation_status, "INVALID")
        self.assertIn("Empty row.", empty.validation_errors)

    # --- review ---
    @override_settings(IS_VERCEL=False)
    def test_digital_review_page_shows_summary_and_staged_records(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        sf = self.upload_and_get_file(batch)
        data = self.default_mapping(sf)
        data["validate_stage"] = "1"
        self.client.post(reverse("record_migration:column_mapping", args=[batch.pk, sf.pk]), data)
        resp = self.client.get(reverse("record_migration:digital_review", args=[batch.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Total spreadsheet rows")
        self.assertContains(resp, "Jane Doe")
        self.assertContains(resp, "Valid")

    @override_settings(IS_VERCEL=False)
    def test_staged_record_detail_accessible(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        sf = self.upload_and_get_file(batch)
        data = self.default_mapping(sf)
        data["validate_stage"] = "1"
        self.client.post(reverse("record_migration:column_mapping", args=[batch.pk, sf.pk]), data)
        rec = batch.records.get()
        resp = self.client.get(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Original source values")
        self.assertContains(resp, "Jane Doe")

    # --- draft removal ---
    @override_settings(IS_VERCEL=False)
    def test_remove_file_allowed_only_for_draft_digital_batch(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        sf = self.upload_and_get_file(batch)
        # batch becomes UPLOADED after upload; removal not allowed per status rule
        resp = self.client.post(reverse("record_migration:remove_spreadsheet", args=[batch.pk, sf.pk]))
        self.assertEqual(resp.status_code, 403)
        # make draft again to allow removal
        batch.status = MigrationBatch.Status.DRAFT
        batch.save(update_fields=["status"])
        resp = self.client.post(reverse("record_migration:remove_spreadsheet", args=[batch.pk, sf.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(batch.files.exists())
        self.assertTrue(MigrationAuditLog.objects.filter(batch=batch, action="spreadsheet_removed").exists())

    # --- receptionist restrictions on review ---
    @override_settings(IS_VERCEL=False)
    def test_receptionist_cannot_access_digital_review(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.doctor)
        sf = self.upload_and_get_file(batch)
        data = self.default_mapping(sf)
        data["validate_stage"] = "1"
        self.client.post(reverse("record_migration:column_mapping", args=[batch.pk, sf.pk]), data)
        self.client.force_login(self.receptionist)
        self.assertEqual(self.client.get(reverse("record_migration:digital_review", args=[batch.pk])).status_code, 403)

    # --- create flow ---
    def test_create_digital_batch_redirects_to_spreadsheet_upload(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("record_migration:create_batch"),
            {
                "name": "Digital Import 1",
                "migration_type": MigrationBatch.MigrationType.DIGITAL,
                "source_hospital": "Clinic",
                "source_department": "",
                "source_system": "OldSys",
                "description": "test",
            },
        )
        batch = MigrationBatch.objects.get(name="Digital Import 1")
        self.assertRedirects(resp, reverse("record_migration:upload_spreadsheet", args=[batch.pk]))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RecordMigrationPart3Tests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="adminmig3", password="StrongPass123!", role=User.Role.ADMIN,
            is_approved=True, is_active=True, first_name="Admin", last_name="Three",
        )
        self.doctor = User.objects.create_user(
            username="doctormig3", password="StrongPass123!", role=User.Role.DOCTOR,
            is_approved=True, is_active=True, first_name="Doc", last_name="Three",
        )
        self.reviewer = User.objects.create_user(
            username="reviewermig3", password="StrongPass123!", role=User.Role.DOCTOR,
            is_approved=True, is_active=True, first_name="Reviewer", last_name="Three",
        )
        self.other_doctor = User.objects.create_user(
            username="otherdocmig3", password="StrongPass123!", role=User.Role.DOCTOR,
            is_approved=True, is_active=True,
        )
        self.receptionist = User.objects.create_user(
            username="receptionmig3", password="StrongPass123!", role=User.Role.RECEPTIONIST,
            is_approved=True, is_active=True,
        )

    def create_digital_batch(self, user=None, status=None):
        owner = user or self.doctor
        return MigrationBatch.objects.create(
            name="Digital Batch P3",
            migration_type=MigrationBatch.MigrationType.DIGITAL,
            source_hospital="Old Hospital",
            description="Part 3",
            status=status or MigrationBatch.Status.DRAFT,
            created_by=owner,
        )

    def mapping_data(self, source_file, include_pid=False, extra=None):
        headers = source_file.column_headers or []
        data = {}
        def pick(options):
            for h in headers:
                if h in options:
                    return h
            return ""
        data["map_full_name"] = pick(["Full Name", "Name", "full_name"])
        data["map_date_of_birth"] = pick(["Date of Birth", "DOB", "date_of_birth"])
        data["map_sex"] = pick(["Sex", "Gender", "sex"])
        data["map_phone_number"] = pick(["Phone", "Phone Number", "phone_number"])
        if include_pid:
            data["map_patient_id"] = pick(["Patient Number", "Patient ID", "patient_id"])
        if extra:
            data.update(extra)
        return data

    @override_settings(IS_VERCEL=False)
    def stage_rows(self, batch, user, rows=None, header=None, include_pid=False, extra_map=None):
        self.client.force_login(user)
        f = make_csv_file(rows=rows, header=header) if (rows or header) else make_csv_file()
        resp = self.client.post(
            reverse("record_migration:upload_spreadsheet", args=[batch.pk]),
            {"file": f},
        )
        self.assertEqual(resp.status_code, 302)
        sf = batch.files.latest("id")
        data = self.mapping_data(sf, include_pid=include_pid, extra=extra_map)
        data["validate_stage"] = "1"
        resp = self.client.post(reverse("record_migration:column_mapping", args=[batch.pk, sf.pk]), data)
        self.assertEqual(resp.status_code, 302)
        return sf

    # --- matching ---
    @override_settings(IS_VERCEL=False)
    def test_existing_patient_match_by_reliable_patient_number(self):
        existing = Patient.objects.create(full_name="Alice Match", date_of_birth="1980-05-05", sex=Patient.Sex.FEMALE)
        batch = self.create_digital_batch(user=self.doctor)
        self.stage_rows(
            batch, self.doctor,
            rows=[[existing.patient_id, "Alice Match", "1980-05-05", "F", "111"]],
            header=["Patient Number", "Full Name", "Date of Birth", "Sex", "Phone"],
            include_pid=True,
        )
        rec = batch.records.get()
        self.assertEqual(rec.review_status, MigrationRecord.ReviewStatus.EXISTING_PATIENT_MATCH)
        self.assertTrue(any(c.get("strength") == "exact" and c.get("patient_number") == existing.patient_id for c in rec.match_candidates))

    @override_settings(IS_VERCEL=False)
    def test_name_dob_suggests_possible_duplicate_not_auto_merge(self):
        existing = Patient.objects.create(full_name="Bob Same", date_of_birth="1975-01-01", sex=Patient.Sex.MALE)
        batch = self.create_digital_batch(user=self.doctor)
        self.stage_rows(
            batch, self.doctor,
            rows=[["Bob Same", "1975-01-01", "M", "222"]],
            header=["Full Name", "Date of Birth", "Sex", "Phone"],
        )
        rec = batch.records.get()
        self.assertEqual(rec.review_status, MigrationRecord.ReviewStatus.POSSIBLE_DUPLICATE)
        self.assertTrue(any(c.get("patient_id") == existing.pk for c in rec.match_candidates))
        self.assertEqual(rec.decision, MigrationRecord.Decision.NONE)

    @override_settings(IS_VERCEL=False)
    def test_new_patient_suggested_when_no_match(self):
        batch = self.create_digital_batch(user=self.doctor)
        self.stage_rows(batch, self.doctor)
        rec = batch.records.get()
        self.assertEqual(rec.review_status, MigrationRecord.ReviewStatus.NEW_PATIENT)

    @override_settings(IS_VERCEL=False)
    def test_duplicate_rows_and_already_imported_detected(self):
        existing = Patient.objects.create(full_name="Dup Target", date_of_birth="1991-02-02", sex=Patient.Sex.MALE)
        batch = self.create_digital_batch(user=self.doctor)
        # in-file duplicates
        self.stage_rows(
            batch, self.doctor,
            rows=[["Jane Dup", "1990-01-01", "F", "1"], ["Jane Dup", "1990-01-01", "F", "1"]],
            header=["Full Name", "Date of Birth", "Sex", "Phone"],
        )
        recs = list(batch.records.order_by("row_number"))
        self.assertTrue(recs[1].is_duplicate_in_file)
        self.assertEqual(recs[1].validation_status, MigrationRecord.ValidationStatus.INVALID)
        # already imported by patient number
        batch2 = self.create_digital_batch(user=self.doctor)
        self.stage_rows(
            batch2, self.doctor,
            rows=[[existing.patient_id, "Dup Target", "1991-02-02", "M", "9"]],
            header=["Patient Number", "Full Name", "Date of Birth", "Sex", "Phone"],
            include_pid=True,
        )
        rec2 = batch2.records.get()
        rec2.is_imported = True
        rec2.review_status = MigrationRecord.ReviewStatus.IMPORTED
        rec2.imported_patient = existing
        rec2.save()
        batch3 = self.create_digital_batch(user=self.doctor)
        self.stage_rows(
            batch3, self.doctor,
            rows=[[existing.patient_id, "Dup Target", "1991-02-02", "M", "9"]],
            header=["Patient Number", "Full Name", "Date of Birth", "Sex", "Phone"],
            include_pid=True,
        )
        rec3 = batch3.records.get()
        self.assertTrue(any("already imported" in c.lower() for c in (rec3.conflicts or [])))

    # --- decisions / review UI access ---
    @override_settings(IS_VERCEL=False)
    def test_receptionist_cannot_access_matching_review_or_actions(self):
        batch = self.create_digital_batch(user=self.doctor)
        self.stage_rows(batch, self.doctor)
        rec = batch.records.get()
        self.client.force_login(self.receptionist)
        self.assertEqual(self.client.get(reverse("record_migration:digital_review", args=[batch.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("record_migration:run_matching", args=[batch.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "save_decision", "decision": "CREATE_NEW"}).status_code, 403)

    @override_settings(IS_VERCEL=False)
    def test_save_decisions_link_new_flag_reject_with_reason(self):
        existing = Patient.objects.create(full_name="Link Me", date_of_birth="1988-03-03", sex=Patient.Sex.FEMALE)
        batch = self.create_digital_batch(user=self.doctor)
        self.stage_rows(
            batch, self.doctor,
            rows=[["Link Me", "1988-03-03", "F", "333"]],
            header=["Full Name", "Date of Birth", "Sex", "Phone"],
        )
        rec = batch.records.get()
        # link existing
        self.client.force_login(self.doctor)
        resp = self.client.post(
            reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]),
            {"action": "save_decision", "decision": "LINK_EXISTING", "matched_patient_id": existing.pk, "reason": "Same person"},
        )
        self.assertEqual(resp.status_code, 302)
        rec.refresh_from_db()
        self.assertEqual(rec.decision, MigrationRecord.Decision.LINK_EXISTING)
        self.assertEqual(rec.matched_patient_id, existing.pk)
        self.assertEqual(rec.decision_reason, "Same person")
        self.assertTrue(MigrationAuditLog.objects.filter(batch=batch, record=rec, action="match_decision_saved").exists())
        # flag requires reason
        resp = self.client.post(
            reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]),
            {"action": "save_decision", "decision": "FLAG", "reason": ""},
        )
        self.assertEqual(resp.status_code, 200)
        rec.refresh_from_db()
        self.assertEqual(rec.decision, MigrationRecord.Decision.LINK_EXISTING)  # unchanged
        resp = self.client.post(
            reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]),
            {"action": "save_decision", "decision": "FLAG", "reason": "Needs investigation"},
        )
        self.assertEqual(resp.status_code, 302)
        rec.refresh_from_db()
        self.assertEqual(rec.review_status, MigrationRecord.ReviewStatus.NEEDS_REVIEW)
        # reject
        resp = self.client.post(
            reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]),
            {"action": "save_decision", "decision": "REJECT", "reason": "Bad record"},
        )
        self.assertEqual(resp.status_code, 302)
        rec.refresh_from_db()
        self.assertEqual(rec.review_status, MigrationRecord.ReviewStatus.REJECTED)
        self.assertEqual(rec.decision, MigrationRecord.Decision.REJECT)

    @override_settings(IS_VERCEL=False)
    def test_conflicting_information_flagged_no_silent_overwrite(self):
        existing = Patient.objects.create(full_name="Conflict Name", date_of_birth="1980-01-01", sex=Patient.Sex.MALE, phone_number="000")
        batch = self.create_digital_batch(user=self.doctor)
        self.stage_rows(
            batch, self.doctor,
            rows=[[existing.patient_id, "Different Name", "1980-01-01", "M", "999"]],
            header=["Patient Number", "Full Name", "Date of Birth", "Sex", "Phone"],
            include_pid=True,
        )
        rec = batch.records.get()
        self.client.force_login(self.doctor)
        self.client.post(
            reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]),
            {"action": "save_decision", "decision": "LINK_EXISTING", "matched_patient_id": existing.pk, "reason": "Same ID"},
        )
        rec.refresh_from_db()
        self.assertTrue(len(rec.conflicts) > 0)
        self.assertEqual(rec.review_status, MigrationRecord.ReviewStatus.NEEDS_REVIEW)
        existing.refresh_from_db()
        self.assertEqual(existing.full_name, "Conflict Name")
        self.assertEqual(existing.phone_number, "000")

    # --- approval & import ---
    @override_settings(IS_VERCEL=False)
    def test_approval_requires_decision_and_separate_reviewer(self):
        batch = self.create_digital_batch(user=self.doctor)
        self.stage_rows(batch, self.doctor)
        rec = batch.records.get()
        # uploader (doctor) cannot approve own file
        self.client.force_login(self.doctor)
        self.client.post(
            reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]),
            {"action": "save_decision", "decision": "CREATE_NEW", "reason": "new"},
        )
        resp = self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "approve"})
        self.assertEqual(resp.status_code, 200)
        rec.refresh_from_db()
        self.assertIsNone(rec.approved_by)
        self.assertNotEqual(rec.review_status, MigrationRecord.ReviewStatus.READY_FOR_APPROVAL)
        # separate authorised reviewer (admin, has access) can approve
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "approve"})
        self.assertEqual(resp.status_code, 302)
        rec.refresh_from_db()
        self.assertEqual(rec.approved_by, self.admin)
        self.assertEqual(rec.review_status, MigrationRecord.ReviewStatus.READY_FOR_APPROVAL)
        self.assertTrue(MigrationAuditLog.objects.filter(batch=batch, record=rec, action="record_approved").exists())

    @override_settings(IS_VERCEL=False)
    def test_possible_duplicate_cannot_be_approved_without_resolution(self):
        Patient.objects.create(full_name="Poss Dup", date_of_birth="1977-07-07", sex=Patient.Sex.MALE)
        batch = self.create_digital_batch(user=self.doctor)
        self.stage_rows(batch, self.doctor, rows=[["Poss Dup", "1977-07-07", "M", "1"]], header=["Full Name", "Date of Birth", "Sex", "Phone"])
        rec = batch.records.get()
        self.assertEqual(rec.review_status, MigrationRecord.ReviewStatus.POSSIBLE_DUPLICATE)
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "approve"})
        self.assertEqual(resp.status_code, 200)
        rec.refresh_from_db()
        self.assertIsNone(rec.approved_by)

    @override_settings(IS_VERCEL=False)
    def test_import_creates_new_patient_and_is_idempotent(self):
        batch = self.create_digital_batch(user=self.doctor)
        self.stage_rows(batch, self.doctor)
        rec = batch.records.get()
        self.client.force_login(self.doctor)
        self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "save_decision", "decision": "CREATE_NEW", "reason": "new"})
        self.client.force_login(self.admin)
        self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "approve"})
        before = Patient.objects.count()
        resp = self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "import"})
        self.assertEqual(resp.status_code, 302)
        rec.refresh_from_db()
        self.assertTrue(rec.is_imported)
        self.assertIsNotNone(rec.imported_patient)
        self.assertEqual(Patient.objects.count(), before + 1)
        self.assertTrue(MigrationAuditLog.objects.filter(batch=batch, record=rec, action="record_imported").exists())
        # repeat import does not duplicate
        resp = self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "import"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Patient.objects.count(), before + 1)

    @override_settings(IS_VERCEL=False)
    def test_import_links_to_existing_patient_without_overwrite(self):
        existing = Patient.objects.create(full_name="Keep Original", date_of_birth="1982-02-02", sex=Patient.Sex.FEMALE, phone_number="123")
        batch = self.create_digital_batch(user=self.doctor)
        self.stage_rows(
            batch, self.doctor,
            rows=[["Keep Original", "1982-02-02", "F", "123"]],
            header=["Full Name", "Date of Birth", "Sex", "Phone"],
        )
        rec = batch.records.get()
        self.client.force_login(self.doctor)
        self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "save_decision", "decision": "LINK_EXISTING", "matched_patient_id": existing.pk, "reason": "match"})
        self.client.force_login(self.admin)
        self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "approve"})
        before = Patient.objects.count()
        resp = self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "import"})
        self.assertEqual(resp.status_code, 302)
        rec.refresh_from_db()
        existing.refresh_from_db()
        self.assertTrue(rec.is_imported)
        self.assertEqual(rec.imported_patient_id, existing.pk)
        self.assertEqual(Patient.objects.count(), before)
        self.assertEqual(existing.full_name, "Keep Original")

    @override_settings(IS_VERCEL=False)
    def test_rejected_record_cannot_be_approved_or_imported(self):
        batch = self.create_digital_batch(user=self.doctor)
        self.stage_rows(batch, self.doctor)
        rec = batch.records.get()
        self.client.force_login(self.doctor)
        self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "save_decision", "decision": "REJECT", "reason": "no"})
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "approve"})
        self.assertEqual(resp.status_code, 200)
        rec.refresh_from_db()
        self.assertIsNone(rec.approved_by)
        self.assertFalse(rec.is_imported)

    @override_settings(IS_VERCEL=False)
    def test_import_rollback_on_failure(self):
        from unittest.mock import patch
        batch = self.create_digital_batch(user=self.doctor)
        self.stage_rows(batch, self.doctor)
        rec = batch.records.get()
        self.client.force_login(self.doctor)
        self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "save_decision", "decision": "CREATE_NEW", "reason": "new"})
        self.client.force_login(self.admin)
        self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "approve"})
        before = Patient.objects.count()
        with patch("record_migration.models.MigrationAuditLog.objects.create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "import"})
        rec.refresh_from_db()
        self.assertFalse(rec.is_imported)
        self.assertEqual(Patient.objects.count(), before)

    @override_settings(IS_VERCEL=False)
    def test_import_blocks_existing_patient_number_duplicate(self):
        existing = Patient.objects.create(full_name="Existing Num", date_of_birth="1970-01-01", sex=Patient.Sex.MALE)
        batch = self.create_digital_batch(user=self.doctor)
        # stage as NEW patient but with mapped patient_id colliding
        self.stage_rows(
            batch, self.doctor,
            rows=[[existing.patient_id, "New Person", "1995-05-05", "F", "5"]],
            header=["Patient Number", "Full Name", "Date of Birth", "Sex", "Phone"],
            include_pid=True,
        )
        rec = batch.records.get()
        # force decision to create new despite match suggestion for test of safeguard
        from django.utils import timezone
        rec.review_status = MigrationRecord.ReviewStatus.NEW_PATIENT
        rec.decision = MigrationRecord.Decision.CREATE_NEW
        rec.decision_reason = "force"
        rec.conflicts = []
        rec.matched_patient = None
        rec.approved_by = self.admin
        rec.approved_at = timezone.now()
        rec.review_status = MigrationRecord.ReviewStatus.READY_FOR_APPROVAL
        rec.save()
        self.client.force_login(self.admin)
        before = Patient.objects.count()
        resp = self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "import"})
        self.assertEqual(resp.status_code, 200)
        rec.refresh_from_db()
        self.assertFalse(rec.is_imported)
        self.assertEqual(Patient.objects.count(), before)
        self.assertEqual(rec.review_status, MigrationRecord.ReviewStatus.POSSIBLE_DUPLICATE)

    @override_settings(IS_VERCEL=False)
    def test_doctor_cannot_act_on_other_doctors_batch(self):
        batch = self.create_digital_batch(user=self.doctor)
        self.stage_rows(batch, self.doctor)
        rec = batch.records.get()
        self.client.force_login(self.other_doctor)
        self.assertEqual(self.client.get(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "save_decision", "decision": "CREATE_NEW"}).status_code, 403)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RecordMigrationPart4Tests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="adminmig4", password="StrongPass123!", role=User.Role.ADMIN,
            is_approved=True, is_active=True, first_name="Admin", last_name="Four",
        )
        self.doctor = User.objects.create_user(
            username="doctormig4", password="StrongPass123!", role=User.Role.DOCTOR,
            is_approved=True, is_active=True, first_name="Doc", last_name="Four",
        )
        self.reviewer = User.objects.create_user(
            username="reviewermig4", password="StrongPass123!", role=User.Role.DOCTOR,
            is_approved=True, is_active=True, first_name="Reviewer", last_name="Four",
        )
        self.receptionist = User.objects.create_user(
            username="receptionmig4", password="StrongPass123!", role=User.Role.RECEPTIONIST,
            is_approved=True, is_active=True,
        )

    def create_digital_batch(self, user=None):
        owner = user or self.doctor
        return MigrationBatch.objects.create(
            name="Digital Batch P4",
            migration_type=MigrationBatch.MigrationType.DIGITAL,
            source_hospital="Old Hospital",
            description="Part 4",
            status=MigrationBatch.Status.DRAFT,
            created_by=owner,
        )

    @override_settings(IS_VERCEL=False)
    def stage_rows(self, batch, user, rows=None, header=None):
        self.client.force_login(user)
        f = make_csv_file(rows=rows, header=header) if (rows or header) else make_csv_file()
        resp = self.client.post(reverse("record_migration:upload_spreadsheet", args=[batch.pk]), {"file": f})
        self.assertEqual(resp.status_code, 302)
        sf = batch.files.latest("id")
        data = {}
        headers = sf.column_headers or []
        def pick(options):
            for h in headers:
                if h in options:
                    return h
            return ""
        data["map_full_name"] = pick(["Full Name", "Name", "full_name"])
        data["map_date_of_birth"] = pick(["Date of Birth", "DOB", "date_of_birth"])
        data["map_sex"] = pick(["Sex", "Gender", "sex"])
        data["map_phone_number"] = pick(["Phone", "Phone Number", "phone_number"])
        data["validate_stage"] = "1"
        resp = self.client.post(reverse("record_migration:column_mapping", args=[batch.pk, sf.pk]), data)
        self.assertEqual(resp.status_code, 302)
        return sf

    def test_dashboard_shows_aggregated_statistics_and_recent_activity(self):
        batch = self.create_digital_batch()
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("record_migration:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Total migration batches")
        self.assertContains(resp, "Total uploaded files")
        self.assertContains(resp, "Total records processed")
        self.assertContains(resp, "Successfully imported")
        self.assertContains(resp, "Rejected records")
        self.assertContains(resp, batch.name)
        self.assertContains(resp, batch.get_migration_type_display())

    @override_settings(IS_VERCEL=False)
    def test_batch_report_contains_details_and_statistics(self):
        batch = self.create_digital_batch(user=self.doctor)
        self.stage_rows(batch, self.doctor, rows=[["", "bad", "X", "1"]], header=["Full Name", "Date of Birth", "Sex", "Phone"])
        self.client.force_login(self.doctor)
        resp = self.client.get(reverse("record_migration:batch_report", args=[batch.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, batch.name)
        self.assertContains(resp, "Digital records")
        self.assertContains(resp, "Old Hospital")
        self.assertContains(resp, "Total files uploaded")
        self.assertContains(resp, "Total records processed")
        self.assertContains(resp, "Invalid records")
        self.assertContains(resp, "Final status")
        self.assertContains(resp, "Staff who reviewed or approved")

    @override_settings(IS_VERCEL=False)
    def test_error_report_csv_download_omits_patient_mapped_values(self):
        batch = self.create_digital_batch(user=self.doctor)
        self.stage_rows(batch, self.doctor, rows=[["", "bad", "X", "1"]], header=["Full Name", "Date of Birth", "Sex", "Phone"])
        self.client.force_login(self.doctor)
        resp = self.client.get(reverse("record_migration:download_error_report", args=[batch.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("attachment", resp["Content-Disposition"])
        content = resp.content.decode("utf-8")
        self.assertIn("Spreadsheet row number", content)
        self.assertIn("Error type", content)
        self.assertIn("Validation error", content)
        self.assertNotIn("Full Name", content.splitlines()[0])  # header has no patient fields
        self.assertNotIn("+263", content)  # no phone/mapped patient values
        self.assertTrue(MigrationAuditLog.objects.filter(batch=batch, action="error_report_downloaded").exists())

    @override_settings(IS_VERCEL=False)
    def test_history_filters_and_pagination(self):
        for i in range(30):
            MigrationBatch.objects.create(
                name=f"Batch {i}", migration_type=MigrationBatch.MigrationType.PAPER,
                status=MigrationBatch.Status.DRAFT, created_by=self.admin,
            )
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("record_migration:history"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["page_obj"].paginator.num_pages >= 2)
        resp2 = self.client.get(reverse("record_migration:history"), {"migration_type": "PAPER"})
        self.assertEqual(resp2.status_code, 200)
        resp3 = self.client.get(reverse("record_migration:history"), {"status": "DRAFT", "page": 2})
        self.assertEqual(resp3.status_code, 200)

    @override_settings(IS_VERCEL=False)
    def test_history_outcome_filter_and_staff_filter(self):
        batch = self.create_digital_batch(user=self.doctor)
        self.stage_rows(batch, self.doctor)
        rec = batch.records.get()
        self.client.force_login(self.doctor)
        self.client.post(reverse("record_migration:staged_record_detail", args=[batch.pk, rec.pk]), {"action": "save_decision", "decision": "REJECT", "reason": "no"})
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("record_migration:history"), {"outcome": "rejected"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, batch.name)
        resp2 = self.client.get(reverse("record_migration:history"), {"staff": str(self.doctor.pk)})
        self.assertEqual(resp2.status_code, 200)

    def test_batch_report_and_error_download_permissions(self):
        batch = self.create_digital_batch(user=self.doctor)
        self.client.force_login(self.receptionist)
        self.assertEqual(self.client.get(reverse("record_migration:batch_report", args=[batch.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("record_migration:download_error_report", args=[batch.pk])).status_code, 403)
        self.client.force_login(self.reviewer)  # other doctor, not creator
        self.assertEqual(self.client.get(reverse("record_migration:batch_report", args=[batch.pk])).status_code, 403)

    @override_settings(IS_VERCEL=False)
    def test_paper_workflow_still_secure_and_functional(self):
        # create paper batch and upload as admin
        paper = MigrationBatch.objects.create(
            name="Paper P4", migration_type=MigrationBatch.MigrationType.PAPER,
            status=MigrationBatch.Status.DRAFT, created_by=self.admin,
        )
        # attach requires existing patient
        from appointments.models import QueueEntry
        patient = Patient.objects.create(full_name="Paper Patient", date_of_birth="1990-01-01", sex=Patient.Sex.FEMALE)
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("record_migration:upload_document", args=[paper.pk]),
            {"patient": patient.pk, "file": make_pdf_file("paper.pdf"), "document_date": "2018-01-01", "source": "Archive", "description": "scan"},
        )
        self.assertEqual(resp.status_code, 302)
        doc = MigrationDocument.objects.get(batch=paper)
        self.assertEqual(doc.original_filename, "paper.pdf")
        self.client.force_login(self.receptionist)
        self.assertEqual(self.client.get(reverse("record_migration:download_document", args=[doc.pk])).status_code, 403)

    @override_settings(IS_VERCEL=False)
    def test_audit_history_has_no_modification_endpoints(self):
        # no delete/edit views exist for audit logs; history is read-only page
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("record_migration:history"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Delete audit")
        self.assertNotContains(resp, "Edit audit")
