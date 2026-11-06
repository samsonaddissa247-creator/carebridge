from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import User
from .forms import ConsultationRecordForm, MedicalHistoryForm, PatientForm, VitalSignsForm
from .models import ConsultationRecord, MedicalHistory, MedicalRecordAuditLog, Patient, VitalSigns


def can_view_patients(user):
    return user.is_authenticated and user.role in {User.Role.ADMIN, User.Role.DOCTOR, User.Role.RECEPTIONIST}


def can_manage_patients(user):
    return user.is_authenticated and user.role in {User.Role.ADMIN, User.Role.RECEPTIONIST}


def can_view_medical_records(user):
    return user.is_authenticated and user.role in {User.Role.ADMIN, User.Role.DOCTOR, User.Role.RECEPTIONIST}


def can_manage_medical_records(user):
    return user.is_authenticated and user.role in {User.Role.DOCTOR, User.Role.ADMIN}


def log_medical_record_action(patient, actor, action, details=""):
    MedicalRecordAuditLog.objects.create(patient=patient, actor=actor, action=action, details=details)


@login_required
@user_passes_test(can_manage_patients)
@require_http_methods(["GET", "POST"])
def register_patient(request):
    form = PatientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        patient = form.save(commit=False)
        patient.registered_by = request.user
        patient.save()
        messages.success(request, f"Patient registered successfully. ID: {patient.patient_id}")
        return redirect("patient_detail", pk=patient.pk)
    return render(request, "patients/register.html", {"form": form})


@login_required
@user_passes_test(can_view_patients)
@require_http_methods(["GET"])
def patient_list(request):
    query = request.GET.get("q", "")
    patients = Patient.objects.all()
    if query:
        patients = patients.filter(full_name__icontains=query) | patients.filter(patient_id__icontains=query)
    return render(request, "patients/list.html", {"patients": patients, "query": query})


@login_required
@user_passes_test(can_view_patients)
@require_http_methods(["GET"])
def patient_detail(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    if request.user.role == User.Role.RECEPTIONIST and request.user != patient.registered_by:
        messages.error(request, "You do not have permission to view this patient record.")
        return redirect("patient_list")
    medical_history = patient.medical_histories.order_by("-updated_at").first()
    consultations = patient.consultations.select_related("doctor").all()
    vital_signs = patient.vital_signs.select_related("recorded_by").all()
    return render(
        request,
        "patients/detail.html",
        {
            "patient": patient,
            "medical_history": medical_history,
            "consultations": consultations,
            "vital_signs": vital_signs,
        },
    )


@login_required
@user_passes_test(can_manage_patients)
@require_http_methods(["GET", "POST"])
def update_patient(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    form = PatientForm(request.POST or None, instance=patient)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Patient record updated for {patient.full_name}.")
        return redirect("patient_detail", pk=patient.pk)
    return render(request, "patients/update.html", {"form": form, "patient": patient})


@login_required
@user_passes_test(can_manage_medical_records)
@require_http_methods(["GET", "POST"])
def add_medical_history(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    if request.user.role == User.Role.DOCTOR:
        if not patient.consultations.filter(doctor=request.user).exists():
            messages.error(request, "You can only add medical history for patients you are authorised to attend.")
            return redirect("patient_detail", pk=patient.pk)
    form = MedicalHistoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        history = form.save(commit=False)
        history.patient = patient
        history.recorded_by = request.user
        history.save()
        log_medical_record_action(patient, request.user, "medical_history_created", f"Medical history created for {patient.full_name}.")
        messages.success(request, "Medical history added.")
        return redirect("patient_detail", pk=patient.pk)
    return render(request, "patients/add_medical_history.html", {"form": form, "patient": patient})


@login_required
@user_passes_test(can_manage_medical_records)
@require_http_methods(["GET", "POST"])
def add_consultation(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    if request.user.role == User.Role.DOCTOR and not patient.appointments.filter(doctor=request.user).exists():
        messages.error(request, "You can only create consultation records for your authorised patients.")
        return redirect("patient_detail", pk=patient.pk)
    form = ConsultationRecordForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        consultation = form.save(commit=False)
        consultation.patient = patient
        consultation.created_by = request.user
        consultation.save()
        log_medical_record_action(patient, request.user, "consultation_created", f"Consultation created for {patient.full_name}.")
        messages.success(request, "Consultation record created.")
        return redirect("patient_detail", pk=patient.pk)
    return render(request, "patients/add_consultation.html", {"form": form, "patient": patient})


@login_required
@user_passes_test(can_manage_medical_records)
@require_http_methods(["GET", "POST"])
def add_vital_signs(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    if request.user.role == User.Role.DOCTOR and not patient.appointments.filter(doctor=request.user).exists():
        messages.error(request, "You can only record vital signs for your authorised patients.")
        return redirect("patient_detail", pk=patient.pk)
    form = VitalSignsForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        vital_signs = form.save(commit=False)
        vital_signs.patient = patient
        vital_signs.recorded_by = request.user
        vital_signs.save()
        log_medical_record_action(patient, request.user, "vital_signs_recorded", f"Vital signs recorded for {patient.full_name}.")
        messages.success(request, "Vital signs recorded.")
        return redirect("patient_detail", pk=patient.pk)
    return render(request, "patients/add_vital_signs.html", {"form": form, "patient": patient})


@login_required
@user_passes_test(can_view_medical_records)
@require_GET
def medical_record_history(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    if request.user.role == User.Role.RECEPTIONIST and request.user != patient.registered_by:
        messages.error(request, "This record is restricted to authorised clinical staff.")
        return redirect("patient_list")
    history = MedicalHistory.objects.filter(patient=patient).select_related("recorded_by").order_by("-updated_at")
    consultations = ConsultationRecord.objects.filter(patient=patient).select_related("doctor", "created_by").order_by("-consultation_datetime")
    vital_signs = VitalSigns.objects.filter(patient=patient).select_related("recorded_by").order_by("-recorded_at")
    return render(
        request,
        "patients/medical_record_history.html",
        {"patient": patient, "history": history, "consultations": consultations, "vital_signs": vital_signs},
    )


@login_required
@user_passes_test(can_manage_medical_records)
@require_POST
def correct_record(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    details = request.POST.get("details", "").strip()
    if not details:
        messages.error(request, "Please provide a correction note before submitting the record correction.")
        return redirect("patient_detail", pk=patient.pk)
    log_medical_record_action(patient, request.user, "clinical_record_corrected", details)
    messages.success(request, "Medical record correction noted and logged.")
    return redirect("patient_detail", pk=patient.pk)
