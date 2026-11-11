# CareLink

CareLink is a single-facility hospital management system MVP built with Django.
It is a capstone project exploring how a small hospital can replace selected
paper-based administrative workflows with a role-based digital system.

## Problem and proposed solution

Patient registration, appointment scheduling, queue coordination and record
retrieval can rely on paper processes. This can add administrative work and make
coordination slower. CareLink brings those workflows into one application so
authorised staff can find operational information and record work in one place.
It is a demonstrator, not a production-ready clinical information system.

## Features

- Staff sign-in, account requests, administrator approval and role-based pages.
- Patient registration, generated patient numbers, search and demographic
  updates.
- Appointment booking, status tracking and cancellation reasons.
- Daily queue registration and queue status updates.
- Clinical history, consultations and vital signs for authorised staff.
- Laboratory requests, workflow statuses, results and verification.
- Operational dashboards and date-filtered appointment, queue, patient and
  laboratory reports.
- Optional local AI assistance for CareLink guidance and role-scoped operational
  summaries.
- Basic visit invoices.
- Audit entries for important appointment, queue, clinical and laboratory
  actions.

## Roles and access

| Role | Main access |
|---|---|
| Hospital administrator | Staff approvals, facility dashboards, patient and clinical records, laboratory workflow, billing and operational reports |
| Receptionist | Patient registration and demographics, appointments, queues, billing and permitted operational reports; not private medical histories or laboratory results |
| Doctor | Assigned patients, own appointments and queue, clinical records, laboratory follow-up and role-scoped reports |
| Laboratory technician | Laboratory requests, results and verification; laboratory workflow reports |

Access is checked by Django views and forms, not only by hiding navigation links.
Doctors' patient access is limited to patients connected to their appointment,
consultation or assigned queue. Administrators have broad access in this
single-facility MVP; an institution should confirm its actual access policy.

## Technologies

- Python 3.12
- Django 6.1 (the version used for the current local test run)
- SQLite for local development; PostgreSQL can be configured for deployment
- Ollama with `qwen2.5:3b` for optional local AI assistance
- Django templates, HTML, CSS and browser JavaScript

Python dependencies are listed in `requirements.txt`. No paid API is required.
Ollama is optional; the rest of the application works when it is unavailable.

## Project structure

```text
accounts/       Custom staff user, sign-in, approval and role forms
appointments/   Appointment, queue and audit models and workflows
assistant/      Role-scoped summaries and local Ollama adapter
billing/        Basic invoices
core/           Dashboards, reporting queries and tests
laboratory/     Test requests, results, verification and audit trail
patients/       Patient and clinical-record models, forms and workflows
carebridge/     Django settings, root URLs and WSGI/ASGI entry points
api/            Vercel WSGI entry point
templates/      Django templates
static/         CareLink styles and static assets
```

The interface retains the existing CareLink teal/green, white and warm accent
palette. No redesign is part of this final stage.

## Requirements and local installation

Use Python 3.12 and pip. Git is needed to clone the project. Ollama is only
needed if you want to test the AI assistant.

```bash
git clone <repository-url> carelink
cd carelink
python3.12 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
```

CareLink reads configuration from environment variables. It does not load a
`.env` file automatically. For a local development shell:

```bash
export DEBUG=True
export SECRET_KEY="$(./venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(64))')"
export ALLOWED_HOSTS="localhost,127.0.0.1"
```

Run the database migrations:

```bash
./venv/bin/python manage.py migrate
```

The default local database is `db.sqlite3` in the project directory. Keep this
file local: it can contain patient and staff data. Do not copy real patient
information into a demonstration database.

## Administrator account

Create a Django superuser:

```bash
./venv/bin/python manage.py createsuperuser
```

Sign in to `/django-admin/` with that account, open its user record, and set
`role` to **Hospital Administrator**, `is_active` to enabled and `is_approved`
to enabled. Use a unique, strong password. The project does not ship a
production administrator password.

### Optional synthetic demonstration data

The seed script is for a development database only. It refuses to run unless
`DEBUG=True`, `CARELINK_ALLOW_DEMO_DATA=1`, and a separate password is supplied
for each demo role. The script creates fictional patients with no phone numbers
and does not print passwords.

```bash
export CARELINK_ALLOW_DEMO_DATA=1
read -s -p "Demo admin password: " CARELINK_DEMO_ADMIN_PASSWORD; echo; export CARELINK_DEMO_ADMIN_PASSWORD
read -s -p "Demo doctor password: " CARELINK_DEMO_DOCTOR_PASSWORD; echo; export CARELINK_DEMO_DOCTOR_PASSWORD
read -s -p "Demo receptionist password: " CARELINK_DEMO_RECEPTIONIST_PASSWORD; echo; export CARELINK_DEMO_RECEPTIONIST_PASSWORD
read -s -p "Demo pending-user password: " CARELINK_DEMO_PENDING_PASSWORD; echo; export CARELINK_DEMO_PENDING_PASSWORD
./venv/bin/python seed.py
```

Enter a different unique value at each hidden prompt; do not use these
demonstration accounts on a deployed system. The script does not reset existing
users or delete existing data. If a local database was seeded by an older
project version, review and change or remove its old demo accounts before using
it.

## Run CareLink

```bash
./venv/bin/python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/). After signing in, use the
role-specific Dashboard and Reports links. The Django administration page is at
`/django-admin/`.

## Ollama and the AI assistant

The provider is **Ollama** and the model is **Qwen2.5 3B**, model identifier
`qwen2.5:3b`. The Django backend calls Ollama's local `/api/chat` endpoint; the
browser never receives model credentials. No API key is needed.

1. Install Ollama using the instructions for your operating system at
   [ollama.com](https://ollama.com/).
2. Start the local service in a separate terminal if it is not already running:

   ```bash
   ollama serve
   ```

3. Download the model and confirm it is listed:

   ```bash
   ollama pull qwen2.5:3b
   ollama list
   ```

4. Configure and start CareLink in another terminal:

   ```bash
   export CARELINK_AI_MODEL="qwen2.5:3b"
   export CARELINK_OLLAMA_URL="http://127.0.0.1:11434/api/chat"
   export CARELINK_AI_TIMEOUT="20"
   ./venv/bin/python manage.py runserver
   ```

5. Sign in as an authorised staff role and choose **AI Assistant**. Ask a
   CareLink workflow question or a question about figures available to that
   role. For an end-to-end live check, ask for a permitted operational count
   that can be independently compared with the dashboard.

If Ollama is stopped or the model is missing, the assistant shows a
service-unavailable message. Dashboards, reports and other CareLink modules do
not depend on Ollama.

### Responsible AI and privacy

The assistant supports administrative system guidance and operational
summaries only. Operational figures are calculated by CareLink from database
queries scoped to the signed-in role; the model is not the source of the
figures. The assistant must not diagnose, interpret laboratory results,
prescribe medication or make clinical decisions. AI responses can contain
errors and must be checked. Qualified healthcare professionals remain
responsible for clinical decisions.

The application sends only the user's question, bounded conversation context
and aggregate operational values to the configured local Ollama service. It
does not intentionally include patient names, contact details, clinical
histories or laboratory results. A pattern-based input check rejects some
common identifiers, but it cannot detect every name or identifying detail.
Staff must not enter patient information. Conversations are kept in browser
memory only and are not saved to the CareLink database.

## Automated tests and checks

Run the system check, migration checks and test suite:

```bash
./venv/bin/python manage.py check
./venv/bin/python manage.py makemigrations --check --dry-run
./venv/bin/python manage.py migrate --check
./venv/bin/python manage.py test
git diff --check
```

AI provider behavior is mocked in automated tests; those tests do not require
Ollama or make paid API requests. A real response must be verified separately
with Ollama running and the requested model downloaded.

## Security, data handling and legal review

- Passwords are stored with Django's password hashing. Account requests remain
  inactive and unapproved until reviewed by an administrator.
- Django authentication, server-side role checks, CSRF middleware, POST-only
  data-changing actions, bounded AI requests and secure session-cookie
  attributes when `DEBUG=False` are used.
- Keep `SECRET_KEY`, database connection strings and demo passwords outside Git.
  `DEBUG` must be `False` in any deployed environment. Configure a strong
  `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and HTTPS at the
  deployment boundary.
- Use only fictional patient and staff data for demonstrations. Restrict access
  to the SQLite or PostgreSQL database and make encrypted, tested backups
  according to the institution's policy. The project does not configure
  database-at-rest encryption, automated backup retention or disaster recovery.
- Audit entries support review of selected workflow actions; they are not a
  complete security monitoring or tamper-proof audit system.
- This project is not certified as compliant with Zimbabwean law or healthcare
  standards. A qualified Zimbabwean legal/privacy professional and healthcare
  institution must review applicable requirements, retention periods, access
  policies, consent, incident response and deployment safeguards.

## Deployment preparation and limitations

The repository includes a Vercel Python WSGI entry point and routing
configuration. Django settings accept `DATABASE_URL` (also
`POSTGRES_URL`/`POSTGRES_PRISMA_URL`) for PostgreSQL. A deployment needs at
least:

```text
DEBUG=False
SECRET_KEY=<strong secret stored in the host's environment>
ALLOWED_HOSTS=<deployed hostnames>
CSRF_TRUSTED_ORIGINS=<https origins for the deployed site>
DATABASE_URL=<PostgreSQL connection string>
```

Apply migrations to the deployment database before serving traffic. Do not use
SQLite in a serverless deployment. Vercel settings now fail fast unless a
database URL is configured; `DATABASE_URL` must point to a persistent
PostgreSQL database, because serverless local storage is not durable. Static
files, production settings and the selected Vercel/PostgreSQL combination
still need verification in a deployment preview before use. No deployment has
been performed as part of this project stage.

The local Ollama URL points to `127.0.0.1` on the Django host. A Vercel
function cannot reach Ollama running on a developer's computer, so the AI
assistant is not available on the current Vercel architecture. For a complete
deployment, use a persistent Django host with PostgreSQL and Ollama reachable
only over a private network, or keep the AI feature disabled. A local
development/capstone demonstration requires no cloud hosting.

## Known limitations

- This is a single-facility MVP, not a validated production clinical system.
- Patient Records Migration is designed for assisted, auditable migration (upload, staging, human review, approval, controlled import). It is not a certified data-migration or records-compliance solution.
- Ollama's safety filter is pattern-based and cannot guarantee detection of all
  clinical or identifying prompts.
- No live model response was generated during this review because the local
  Ollama endpoint did not respond. Use the setup above to perform a live check
  locally.
- SQLite is suitable for local development only; production database backup,
  restore, monitoring and operational procedures must be supplied by the
  deploying institution.
- Historical status-at-time reports, formal retention automation, multi-site
  operation and institutional compliance review are outside this MVP.

## Patient Records Migration module

The `record_migration` app supports assisted migration of historical records into CareLink while preserving existing modules, models and the current UI style.

### What it does

- **Paper records migration:** upload scanned PDF/JPG/PNG documents and attach them to an existing `Patient` profile with original document date, source and description. Original files are preserved in private storage and served only via authenticated, permission-checked download views.
- **Digital records migration:** upload CSV/XLSX spreadsheets, preview rows/columns, map source columns to real `Patient` fields, validate and stage rows for review. Staged rows never become `Patient` records until explicitly approved and imported.
- **Matching and approval:** suggests existing-patient matches using reliable identifiers (hospital patient number) and name/DOB as review-only suggestions (never auto-merged). Staff can select/link existing patient, mark as new patient, flag for investigation, or reject with reason. Conflicts/possible duplicates require human review; existing patient data is not silently overwritten.
- **Safe import:** approved records only; transactional import with locking/guards prevents duplicate imports and partial creation on failure; import outcomes and decisions are audited.
- **Reporting and history:** migration dashboard statistics (from database records), per-batch reports, row-level error reporting with CSV download (no unnecessary patient information), and read-only migration history/audit with filters and pagination.

### Supported file formats

- Paper: `.pdf`, `.jpg`, `.jpeg`, `.png` (content-validated, size-limited, private storage).
- Digital spreadsheets: `.csv` (UTF-8 text) and `.xlsx` (Excel), with content/format validation, size and row-count limits. Spreadsheet content is treated as untrusted data.

### Required permissions

- Migration dashboard, batches, uploads, preview/mapping/review/approval/import, reports and history: **Hospital Administrator** and **Doctor** only (server-side enforced). Doctors are scoped to migration batches they created (consistent with existing access patterns); administrators can access migration batches.
- Receptionists and laboratory technicians do not have migration access; receptionists must not access private clinical migrated documents.
- Migrated clinical document downloads/listing: **Admin/Doctor** only, with doctor patient-access checks (`patients.permissions.doctor_patient_queryset`). Downloads are private attachments (`X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`) and not exposed as public media URLs.
- Approval requires validation passed, an explicit decision, no unresolved conflicts/possible duplicates, and a **separate reviewer** from the uploader of the source spreadsheet file. Import requires prior approval.
- Audit history is read-only in the UI (no edit/delete actions).

### Workflow

#### Create a migration batch
1. Sign in as Admin or Doctor and open **Records migration**.
2. Select **Create migration batch**.
3. Enter batch name, migration type (**Paper** or **Digital**), source hospital/department/system (as applicable), description and save. Batch is created in Draft and the responsible staff member and timestamp are recorded.

#### Paper records migration
1. Create/open a **Paper** batch and upload a scanned PDF/JPG/PNG.
2. Select an existing patient, provide original document date, source and description.
3. The original file is stored unchanged in private storage and attached to the patient profile; upload is audited. Authorised users can view/download via protected endpoints and the patient record.

#### Digital records migration
1. Create/open a **Digital** batch and upload a CSV/XLSX file (private storage).
2. Preview column headings and sample rows, totals and empty/invalid hints (no import).
3. Map source columns to CareLink `Patient` fields (`patient_id`, `full_name`, `date_of_birth`, `sex`, `phone_number`, `next_of_kin`, `allergies`, `chronic_conditions`, `notes`) as available; save/change mapping before validation.
4. Validate and stage rows: rows are stored as `MigrationRecord` staging records with source/mapped values, row number, validation status/errors and in-file duplicate flags. **No `Patient` records are created or updated at staging.**
5. Review/match: inspect matches/suggestions, record decision (link existing patient, mark new patient, flag, or reject with reason), resolve possible duplicates/conflicts.
6. Approve (separate reviewer) and import approved records only: link to selected existing patient or create a new `Patient` safely. Conflicts block import; existing data is not silently overwritten; repeated import of the same staged record is prevented.

#### View migration reports and history
- **Dashboard:** totals for batches/files/processed/imported/awaiting/rejected/errors/possible duplicates and recent activity (from DB records).
- **Batch report:** batch details, source, dates, creator/reviewers-approvers, file/record counts, imported/rejected/invalid/duplicates/awaiting, final status, and error summary. Error details downloadable as CSV (row number, error type/description, resolution status; excludes unnecessary patient information).
- **History:** read-only batches and audit activities with filters (date range, migration type, batch status, staff member, import outcome) and pagination.

### File storage and privacy considerations

- Uploaded migration files are stored under `MEDIA_ROOT/private_media` (no public `MEDIA_URL` serving). Access is mediated by authenticated, role/permission-checked views.
- Validate file type/content, enforce size/row limits, use safe filenames/UUID storage paths, and treat spreadsheet content as untrusted.
- No uploaded patient records/spreadsheet contents are sent to the AI assistant or external AI services.
- On Vercel/serverless setups without persistent private storage, private uploads are blocked by design; use a persistent host/storage and PostgreSQL for deployments.
- Protect the database, storage and backups per institutional policy; keep `SECRET_KEY`/credentials out of Git. Not certified as legally/clinically compliant without institutional review.

### Known limitations (migration module)

- Migration is assisted and requires human review/approval; matching suggestions (especially name/DOB) are not definitive and never auto-merge.
- Separate-reviewer rule prevents the spreadsheet uploader from approving their own staged records; environments with only one authorised reviewer for a batch may need an additional authorised user.
- New-patient import guards against duplicate patient number/core identity; `Patient.patient_id` remains system-generated (source patient number retained in staged data, not forced as CareLink ID).
- Doctor migration access is batch-creator scoped (consistent with current app behavior).
- `record_migration` migrations (0001–0003) may be unapplied in an existing local DB until `manage.py migrate` is run; apply to the target database before use.
- No OCR, no automatic merge/overwrite, no external AI processing, and no production/compliance certification.

## Capstone demonstration plan

Use the development database and synthetic data only. Prepare four separate
accounts with the roles used in the demonstration; do not share passwords or
use real patient information.

1. Sign in as the administrator and show staff approval and the facility
   dashboard.
2. Sign in as the receptionist; register a fictional patient and book an
   appointment.
3. Add that patient to the queue and show the queue number and status.
4. Sign in as the assigned doctor; open the patient's record, document a
   consultation and vital signs, and create a laboratory request.
5. Sign in as a laboratory technician; progress the request, enter a synthetic
   result and verify it.
6. Return to the authorised doctor and review the result's verification state.
7. Open Reports and demonstrate the daily, weekly, monthly, queue and
   laboratory summaries appropriate to the current role.
8. With Ollama running and `qwen2.5:3b` downloaded, ask the assistant a
   non-clinical workflow question and an operational question; compare reported
   counts with CareLink's dashboard.
9. Demonstrate access restrictions by trying an unassigned doctor's patient
   record and a receptionist's clinical-record or laboratory-result page.
10. Explain that CareLink reduces scattered administrative work by connecting
    registration, appointments, queues, records, laboratory workflow and
    reporting, while staff remain responsible for verifying information and
    making all clinical decisions.
