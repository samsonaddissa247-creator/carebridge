# CareLink — Hospital Management System (School Project)

A single-facility hospital management system built with Python (Django) and SQLite,
replacing paper-based patient records with a simple, role-based digital system.

## Features
- Role-based login: Hospital Administrator, Doctor, Receptionist, Laboratory Technician
- Staff accounts require Administrator approval before login (no self-signup for staff)
- Patient registration with auto-generated patient ID
- Patient search and full record view (history, allergies, conditions)
- Appointment booking and status tracking (Pending → Confirmed → Completed)
- Laboratory test requests, processing statuses, results and verification
- AI-powered administrative guidance and role-scoped operational summaries (local model)
- Basic billing / invoices per visit
- Simple operational reports
- Role-specific dashboards for each account type

## Setup

```bash
cd carebridge
./venv/bin/python manage.py migrate
./venv/bin/python seed.py        # creates demo accounts + sample data
./venv/bin/python manage.py runserver
```

Visit http://127.0.0.1:8000/

## AI assistant (optional local setup)

CareLink uses **Ollama** to call the real **Qwen2.5 3B** language model through
Ollama's local HTTP chat API. It does not use a paid API or require an API key.
The model runs on the same machine as Ollama; the backend rejects configured
model endpoints that are not loopback URLs.

1. Install Ollama using the instructions for your operating system at
   [ollama.com](https://ollama.com/).
2. Download the model once:

   ```bash
   ollama pull qwen2.5:3b
   ```

3. Ensure Ollama is running (normally its local service listens on port 11434).
   If it is not already running as a service, start `ollama serve` in a separate
   terminal. In the terminal where you start Django, configure CareLink if you
   need non-default values:

   ```bash
   export CARELINK_AI_MODEL="qwen2.5:3b"
   export CARELINK_OLLAMA_URL="http://127.0.0.1:11434/api/chat"
   export CARELINK_AI_TIMEOUT="20"
   ```

   Then run `./venv/bin/python manage.py runserver`.

   These settings can also be exported in the shell that starts the application.
   `CARELINK_OLLAMA_URL` must point to a local Ollama endpoint. No AI credential
   is needed or stored.

Without Ollama running or the configured model available, the rest of CareLink
continues to work. Assistant requests return a friendly service-unavailable
message; the application does not substitute a scripted answer for the model.

### AI privacy and limitations

- The assistant is for system guidance and administrative summaries only.
- The backend calculates operational counts from the database, filtered by staff
  role. It never fetches patient names, contact details, records or test results
  into the model context. Aggregate values, the current question and recent
  in-memory conversation text are sent to the local model only.
- Patient-number, phone, email and date-of-birth-like input is rejected. Do not
  enter patient-identifying information. The filter cannot recognize every
  possible name or identifier, so staff must still avoid putting private data
  into questions. Requests are restricted to the local Ollama service; there is
  no third-party AI provider fallback.
- Conversations are held only in the current browser page's memory, are not
  saved to the CareLink database, and are cleared by **New conversation** or
  leaving the page.
- The endpoint requires authentication and CSRF protection. Input is size-limited,
  conversations are bounded, and requests are limited to 10 per user per minute
  using Django's local-memory cache. For a multi-worker deployment, replace this
  with a shared cache before relying on the rate limit operationally.
- The assistant must not diagnose, interpret clinical results, recommend
  treatment, or prescribe medication. A basic safety filter refuses common
  clinical prompts, but it is not a clinical safety system and cannot guarantee
  detection of every unsafe request.
- AI output can be inaccurate. Verify any operational explanation against
  CareLink. This feature is not a substitute for clinical, institutional, legal,
  or privacy review.
- A local Ollama model is not currently available on the Vercel deployment
  configuration. The assistant remains unavailable there unless the deployment
  architecture is changed to run a private local model service; CareLink will
  not send information to a third-party AI provider as a fallback.

## Vercel deployment

Set a PostgreSQL connection string as the Vercel `DATABASE_URL`, `POSTGRES_URL`,
or `POSTGRES_PRISMA_URL` environment variable. Run the migrations against that
database before the first deployment:

```bash
DATABASE_URL="postgresql://..." python manage.py migrate
```

The deployed app falls back to the bundled SQLite database when `DATABASE_URL`
is not configured, but Vercel storage is temporary and account requests or
approvals will not persist reliably in that mode.

## Demo accounts (created by seed.py)

| Role          | Username    | Password    |
|---------------|-------------|-------------|
| Admin         | admin       | admin123    |
| Doctor        | drncube     | doctor123   |
| Receptionist  | reception1  | front123    |
| Pending (blocked demo) | drpending | pending123 |

Try logging in as `drpending` to see the approval-gate in action — then log in as
`admin` and approve the account from the "Staff Approvals" page.

## Project structure
- `accounts/` — custom User model with roles, login, staff approval workflow
- `patients/` — patient registration and records
- `appointments/` — booking and status tracking
- `laboratory/` — laboratory requests, results and audit trail
- `assistant/` — role-scoped administrative summaries and local model integration
- `billing/` — simple invoicing
- `core/` — role-based dashboards and reports
- `templates/`, `static/` — CareLink UI (teal/ochre theme)

## Notes for extending
This is scoped as an MVP for a school project. Documented "future scope" ideas
(multi-facility support, offline sync, blood bank, pharmacy stock, SMS OTP for
patients, etc.) are described in the accompanying proposal document.
