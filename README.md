# CareLink — Hospital Management System (School Project)

A single-facility hospital management system built with Python (Django) and SQLite,
replacing paper-based patient records with a simple, role-based digital system.

## Features
- Role-based login: Hospital Administrator, Doctor, Receptionist
- Staff accounts require Administrator approval before login (no self-signup for staff)
- Patient registration with auto-generated patient ID
- Patient search and full record view (history, allergies, conditions)
- Appointment booking and status tracking (Pending → Confirmed → Completed)
- Basic billing / invoices per visit
- Simple operational reports
- Role-specific dashboards for each account type

## Setup

```bash
pip install django
cd carebridge
python manage.py migrate
python seed.py        # creates demo accounts + sample data
python manage.py runserver
```

Visit http://127.0.0.1:8000/

## Vercel deployment

Set a PostgreSQL connection string as the Vercel `DATABASE_URL` environment
variable. Run the migrations against that database before the first deployment:

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
- `billing/` — simple invoicing
- `core/` — role-based dashboards and reports
- `templates/`, `static/` — CareLink UI (teal/ochre theme)

## Notes for extending
This is scoped as an MVP for a school project. Documented "future scope" ideas
(multi-facility support, offline sync, blood bank, pharmacy stock, SMS OTP for
patients, etc.) are described in the accompanying proposal document.
