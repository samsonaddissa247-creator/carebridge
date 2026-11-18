import re

from accounts.models import User

WELCOME_MESSAGE = (
    "Hello! I'm CareLink Assistant. I can help you understand how to use the "
    "hospital management system. What would you like help with?"
)
UNKNOWN_RESPONSE = (
    "I'm not sure I understand that question yet. I can help with patient registration, "
    "appointments, queue management, medical records, laboratory workflows, reports and "
    "billing. Please try asking about one of these features."
)
CLINICAL_REFUSAL = (
    "I'm unable to provide medical advice or interpret clinical results. "
    "Please consult an authorised healthcare professional."
)
RESTRICTED_FEATURE_RESPONSE = (
    "I can't provide instructions for features that are not available to your role. "
    "Please ask about features you can access in CareLink, or contact your Hospital Administrator if you need access."
)


def _normalize(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _contains_any(text, phrases):
    return any(phrase in text for phrase in phrases)


def _contains_all(text, words):
    return all(word in text for word in words)


CLINICAL_PATTERNS = [
    "diagnos",
    "treat",
    "treatment",
    "prescrib",
    "medicat",
    "medicine",
    "dosage",
    "symptom",
    "disease",
    "illness",
    "pain",
    "interpret lab",
    "interpret test",
    "interpret result",
    "lab result",
    "test result",
    "reference range",
    "what is wrong with",
    "should i take",
    "clinical decision",
]

# (role_set_or_None, keywords_any_groups, response_fn_or_str)
# keywords_any_groups: list of groups; each group is list of phrases where at least one must appear? easier: function


def is_clinical_question(text):
    n = _normalize(text)
    clinical_markers = [
        "diagnos", "treatment", "treat ", "prescrib", "medicat", "medicine",
        "dosage", "symptom", "disease", "illness", "what is wrong",
        "interpret lab", "interpret test", "interpret result", "interpret my",
        "lab results", "test results", "reference range", "clinical decision",
    ]
    if _contains_any(n, clinical_markers):
        # avoid false positives on "laboratory results" workflow questions
        if "view laboratory results" in n or "view lab results" in n or "see lab results" in n:
            if not _contains_any(n, ["interpret", "diagnos", "treat", "medicat", "prescrib", "what is wrong"]):
                return False
        return True
    # "pain" alone can be clinical, but be careful; treat as clinical advice request in most contexts
    if " pain" in f" {n} " and _contains_any(n, ["what", "treat", "medicat", "diagnos", "help with my"]):
        return True
    return False


GENERAL_ANSWERS = {
    "what_is_carelink": (
        "CareLink is a hospital management system that helps staff manage patients, "
        "appointments, queues, laboratory workflows, reports and billing based on their assigned role."
    ),
    "how_to_use": (
        "Sign in with your staff account, then use the navigation menu for the features available to your role. "
        "Common areas include Dashboard, Patients, Appointments, Queue, Laboratory, Billing, Reports and the AI Assistant. "
        "If you cannot access an area, it may be restricted to certain roles."
    ),
    "change_password": (
        "If you need to change your password, contact your Hospital Administrator or use the account/password "
        "management process provided by your facility. For security reasons, staff password resets are handled "
        "by authorised administrators."
    ),
    "cant_access": (
        "Access in CareLink is role-based. You may not have permission for that page, your account may be inactive "
        "or pending approval, or you may need to sign in again. Contact your Hospital Administrator if you believe "
        "you should have access."
    ),
    "features": (
        "Available features depend on your role and may include patient registration, appointments, queue management, "
        "medical records, laboratory workflows, billing, reports, staff approvals and operational summaries. "
        "Use the menu to see what is available to you."
    ),
}


ROLE_FAQ = {
    User.Role.RECEPTIONIST: {
        "register_patient": "Go to Patients and select Register. Enter the patient's details and save. You can register and update permitted patient demographic information.",
        "search_patient": "Go to Patients and use the search/list to find a patient by the available identifiers or name shown in the system.",
        "book_appointment": "Go to Appointments and choose to book a new appointment. Select the patient, doctor, date/time and reason, then save.",
        "cancel_appointment": "Go to Appointments, open the relevant appointment, and use the cancel/update status action if available. Provide a reason when cancelling if required.",
        "add_to_queue": "Go to Queue and add the patient to the queue for the current visit, selecting the appropriate details and doctor/appointment if applicable.",
        "queue_number": "A queue number identifies a patient's place/order in the day's queue. It helps staff track who is waiting, called, in progress or completed.",
        "view_medical_records": "Receptionists can manage permitted registration and front-desk information, but private medical histories/clinical records are restricted. Contact clinical staff or an administrator for authorised access.",
    },
    User.Role.DOCTOR: {
        "view_appointments": "Go to Appointments to view your own appointments. You can review scheduled visits assigned to you.",
        "access_patient_record": "Go to Patients and open a patient you are authorised to attend. Doctors can access records for patients linked to their consultations, appointments or assigned queue.",
        "record_consultation": "Open the authorised patient's record and add a consultation entry with the relevant clinical notes as permitted by your workflow.",
        "add_vital_signs": "Open the authorised patient's record and add vital signs from the available clinical/record actions.",
        "request_lab_test": "From the Laboratory area, create a new laboratory request for a patient you are authorised to attend and enter the test details and priority.",
        "view_lab_results": "Go to Laboratory to review requests and available results for patients/requests you are authorised to access.",
    },
    User.Role.LAB_TECHNICIAN: {
        "view_lab_requests": "Go to Laboratory to view laboratory requests and their current status.",
        "update_test_status": "Open a laboratory request and update its status as the sample/test progresses (for example collected, processing, completed or cancelled as allowed).",
        "lab_statuses": "Common laboratory statuses include Requested, Collected, Processing, Completed and Cancelled. Update status according to the actual progress of the test.",
        "enter_results": "Open a request that is ready for result entry (typically Processing) and save the laboratory result details. A result is required before completion where applicable.",
        "verify_result": "After a result is completed, use the verification action on the request to confirm/verify the result if you are authorised to do so.",
    },
    User.Role.ADMIN: {
        "approve_staff": "Go to Staff Approvals (or pending staff) to review account requests and approve or reject staff accounts as appropriate.",
        "view_stats": "Use the Dashboard and Reports pages to view hospital/operational statistics available to administrators.",
        "generate_reports": "Go to Reports, select the relevant date/filters where available, and view or generate the operational reports provided by CareLink.",
        "manage_roles": "Staff roles and access are managed through administrator/staff management functions. Assign roles according to facility policy and approve accounts appropriately.",
        "monitor_appointments": "Go to Appointments and Dashboard/Reports to monitor scheduled, completed and cancelled appointments.",
        "monitor_queue": "Go to Queue and Dashboard/Reports to monitor patients waiting, in progress and completed in the queue.",
    },
}

# suggested questions per role (label, question text)
SUGGESTED_QUESTIONS = {
    User.Role.RECEPTIONIST: [
        ("What is CareLink?", "What is CareLink?"),
        ("Register a patient", "How do I register a patient?"),
        ("Book an appointment", "How do I book an appointment?"),
        ("Add to queue", "How do I add a patient to the queue?"),
        ("Appointments today", "How many appointments are scheduled today?"),
        ("Patients waiting", "How many patients are waiting?"),
    ],
    User.Role.DOCTOR: [
        ("What is CareLink?", "What is CareLink?"),
        ("My appointments", "How do I view my appointments?"),
        ("Request a lab test", "How do I request a laboratory test?"),
        ("View lab results", "How do I view laboratory results?"),
        ("Appointments today", "How many appointments are scheduled today?"),
        ("Patients waiting", "How many patients are waiting?"),
    ],
    User.Role.LAB_TECHNICIAN: [
        ("What is CareLink?", "What is CareLink?"),
        ("View lab requests", "How do I view laboratory requests?"),
        ("Lab statuses", "What are the laboratory statuses?"),
        ("Enter results", "How do I enter laboratory results?"),
        ("Pending requests", "How many laboratory requests are pending?"),
    ],
    User.Role.ADMIN: [
        ("What is CareLink?", "What is CareLink?"),
        ("Approve staff", "How do I approve staff accounts?"),
        ("View statistics", "How do I view hospital statistics?"),
        ("Generate reports", "How do I generate reports?"),
        ("Appointments today", "How many appointments are scheduled today?"),
        ("Patients waiting", "How many patients are waiting?"),
    ],
}


def _answer_for_role(user, key):
    role_answers = ROLE_FAQ.get(user.role, {})
    if key in role_answers:
        return role_answers[key]
    # restricted: asked about another role's feature
    all_keys = set()
    for answers in ROLE_FAQ.values():
        all_keys.update(answers.keys())
    if key in all_keys:
        return RESTRICTED_FEATURE_RESPONSE
    return None


def _match_operational(n, user, summary):
    if summary is None:
        return "That operational information is currently unavailable."
    # scheduled today
    if "appointment" in n and "today" in n and _contains_any(n, ["how many", "number", "count", "total"]) and _contains_any(n, ["scheduled", "booked", "today"]):
        for k in ("appointments_scheduled_today", "my_appointments_scheduled_today"):
            if k in summary:
                return f"There are {summary[k]} appointment(s) scheduled today."
        return "The number of appointments scheduled today is not available for your role."
    if "appointment" in n and "completed" in n and "today" in n and _contains_any(n, ["how many", "number", "count", "total"]):
        for k in ("appointments_completed_today", "my_appointments_completed_today", "laboratory_requests_completed_today"):
            if "appointment" in k and k in summary:
                return f"There are {summary[k]} appointment(s) completed today."
        # doctor lab completed different; prefer appointment keys
        for k in ("appointments_completed_today", "my_appointments_completed_today"):
            if k in summary:
                return f"There are {summary[k]} appointment(s) completed today."
        return "The number of appointments completed today is not available for your role."
    if _contains_any(n, ["how many", "number", "count", "total"]) and "waiting" in n and _contains_any(n, ["patient", "queue"]):
        for k in ("patients_waiting_today", "my_patients_waiting_today"):
            if k in summary:
                return f"There are {summary[k]} patient(s) waiting today."
        return "The number of patients waiting is not available for your role."
    if "laboratory" in n and "pending" in n and _contains_any(n, ["request", "test"]):
        # admin/doctor have pending aggregates; lab tech has new/collected/processing
        if "laboratory_requests_pending" in summary:
            return f"There are {summary['laboratory_requests_pending']} pending laboratory request(s)."
        if "my_lab_requests_pending" in summary:
            return f"There are {summary['my_lab_requests_pending']} pending laboratory request(s) for you."
        if user.role == User.Role.LAB_TECHNICIAN:
            total = (
                summary.get("laboratory_requests_new", 0)
                + summary.get("laboratory_requests_collected", 0)
                + summary.get("laboratory_requests_processing", 0)
            )
            return f"There are {total} pending laboratory request(s) (new, collected or processing)."
        return "The number of pending laboratory requests is not available for your role."
    return None


def get_faq_response(user, message, summary=None):
    n = _normalize(message)
    if not n:
        return None

    # Operational questions (dynamic, DB-backed)
    if _contains_any(n, ["how many", "number of", "count", "total"]) and _contains_any(
        n, ["appointment", "waiting", "queue", "laboratory", "lab request", "pending", "completed", "scheduled"]
    ):
        op = _match_operational(n, user, summary)
        if op:
            return op

    # General
    if _contains_any(n, ["what is carelink", "what s carelink", "about carelink"]):
        return GENERAL_ANSWERS["what_is_carelink"]
    if _contains_any(n, ["how do i use carelink", "how to use carelink", "using carelink", "how does carelink work"]):
        return GENERAL_ANSWERS["how_to_use"]
    if _contains_any(n, ["change my password", "change password", "reset password", "forgot password", "update password"]):
        return GENERAL_ANSWERS["change_password"]
    if _contains_any(n, ["can t access", "cannot access", "cant access", "access denied", "not authorised", "not authorized", "why can t i", "unable to access", "page access"]):
        return GENERAL_ANSWERS["cant_access"]
    if _contains_any(n, ["what features", "available features", "features are available", "what can i do", "what does carelink offer"]):
        return GENERAL_ANSWERS["features"]

    # Receptionist
    if _contains_any(n, ["register a patient", "register patient", "patient registration", "add a patient", "create patient"]):
        return _answer_for_role(user, "register_patient")
    if _contains_any(n, ["search for a patient", "search patient", "find a patient", "find patient", "look up patient", "lookup patient"]):
        return _answer_for_role(user, "search_patient")
    if _contains_any(n, ["book an appointment", "book appointment", "schedule appointment", "make an appointment", "create appointment"]):
        return _answer_for_role(user, "book_appointment")
    if _contains_any(n, ["cancel an appointment", "cancel appointment", "appointment cancellation"]):
        return _answer_for_role(user, "cancel_appointment")
    if _contains_any(n, ["add a patient to the queue", "add patient to queue", "add to queue", "queue a patient"]):
        return _answer_for_role(user, "add_to_queue")
    if _contains_any(n, ["what is a queue number", "queue number", "queue no"]):
        return _answer_for_role(user, "queue_number")
    if _contains_any(n, ["view medical records", "see medical records", "access medical records"]) and "lab" not in n:
        return _answer_for_role(user, "view_medical_records")

    # Doctor
    if _contains_any(n, ["view my appointments", "see my appointments", "my appointments", "doctor appointments"]):
        return _answer_for_role(user, "view_appointments")
    if _contains_any(n, ["access a patient record", "access patient record", "view patient record", "open patient record", "patient record access"]):
        return _answer_for_role(user, "access_patient_record")
    if _contains_any(n, ["record a consultation", "record consultation", "add consultation", "consultation note"]):
        return _answer_for_role(user, "record_consultation")
    if _contains_any(n, ["add vital signs", "record vital signs", "vital signs", "vitals"]):
        return _answer_for_role(user, "add_vital_signs")
    if _contains_any(n, ["request a laboratory test", "request lab test", "request laboratory", "order lab test", "order laboratory test", "create lab request"]):
        return _answer_for_role(user, "request_lab_test")
    if _contains_any(n, ["view laboratory results", "view lab results", "see laboratory results", "see lab results", "check lab results"]):
        # if not clinical interpretation intent
        if not _contains_any(n, ["interpret", "what does", "mean", "diagnos", "treat"]):
            return _answer_for_role(user, "view_lab_results")

    # Laboratory technician
    if _contains_any(n, ["view laboratory requests", "view lab requests", "see laboratory requests", "laboratory requests list"]):
        return _answer_for_role(user, "view_lab_requests")
    if _contains_any(n, ["update a test status", "update test status", "change test status", "update lab status"]):
        return _answer_for_role(user, "update_test_status")
    if _contains_any(n, ["laboratory statuses", "lab statuses", "test statuses", "what are the laboratory statuses", "status of lab"]):
        return _answer_for_role(user, "lab_statuses")
    if _contains_any(n, ["enter laboratory results", "enter lab results", "add lab results", "record lab results", "input results"]):
        return _answer_for_role(user, "enter_results")
    if _contains_any(n, ["verify a result", "verify result", "verify lab result", "result verification"]):
        return _answer_for_role(user, "verify_result")

    # Administrator
    if _contains_any(n, ["approve staff accounts", "approve staff", "staff approval", "approve accounts"]):
        return _answer_for_role(user, "approve_staff")
    if _contains_any(n, ["view hospital statistics", "hospital statistics", "view statistics", "hospital stats", "view stats"]):
        return _answer_for_role(user, "view_stats")
    if _contains_any(n, ["generate reports", "create reports", "view reports", "run reports", "reports page"]):
        return _answer_for_role(user, "generate_reports")
    if _contains_any(n, ["manage staff roles", "staff roles", "assign roles", "manage roles", "change roles"]):
        return _answer_for_role(user, "manage_roles")
    if _contains_any(n, ["monitor appointments", "track appointments", "appointments overview"]):
        return _answer_for_role(user, "monitor_appointments")
    if _contains_any(n, ["monitor the queue", "monitor queue", "track queue", "queue overview"]):
        return _answer_for_role(user, "monitor_queue")

    # Billing
    if _contains_any(n, ["create an invoice", "create invoice", "make an invoice", "new invoice"]):
        if user.role in {User.Role.ADMIN, User.Role.RECEPTIONIST}:
            return "Go to Billing and select Create Invoice. Choose the patient and enter the service/amount details, then save the invoice."
        return RESTRICTED_FEATURE_RESPONSE
    if _contains_any(n, ["view invoices", "see invoices", "invoice list", "billing invoices"]):
        if user.role in {User.Role.ADMIN, User.Role.RECEPTIONIST}:
            return "Go to Billing to view the list of invoices and their details/status."
        return RESTRICTED_FEATURE_RESPONSE
    if _contains_any(n, ["billing totals", "check billing totals", "invoice totals", "billing summary", "total billed"]):
        if user.role in {User.Role.ADMIN, User.Role.RECEPTIONIST}:
            return "Go to Billing or Reports (if available to you) to review billing totals and invoice summaries. Figures shown are based on recorded invoices."
        return RESTRICTED_FEATURE_RESPONSE

    return None


def get_suggested_questions(user):
    return SUGGESTED_QUESTIONS.get(user.role, SUGGESTED_QUESTIONS[User.Role.ADMIN])
