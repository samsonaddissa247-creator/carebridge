from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.models import User
from .forms import ConsultationRecordForm, MedicalHistoryForm, PatientForm, VitalSignsForm
from .models import ConsultationRecord, MedicalHistory, MedicalRecordAuditLog, Patient, VitalSigns
from .permissions import doctor_patient_queryset


def can_view_patients(user):
    return user.is_authenticated and user.role in {User.Role.ADMIN, User.Role.DOCTOR, User.Role.RECEPTIONIST}


def can_manage_patients(user):
    return user.is_authenticated and user.role in {User.Role.ADMIN, User.Role.RECEPTIONIST}


def can_view_medical_records(user):
    return user.is_authenticated and user.role in {User.Role.ADMIN, User.Role.DOCTOR}


def can_manage_medical_records(user):
    return user.is_authenticated and user.role in {User.Role.DOCTOR, User.Role.ADMIN}


def log_medical_record_action(patient, actor, action, details=""):
    MedicalRecordAuditLog.objects.create(patient=patient, actor=actor, action=action, details=details)


def get_accessible_patient(user, pk):
    patients = Patient.objects.all()
    if user.role == User.Role.DOCTOR:
        patients = doctor_patient_queryset(user)
    elif user.role == User.Role.RECEPTIONIST:
        patients = patients.filter(registered_by=user)
    return get_object_or_404(patients, pk=pk)


@login_required
@user_passes_test(can_manage_patients)
@require_http_methods(["GET", "POST"])
def register_patient(request):
    form = PatientForm(request.POST or None, user=request.user)
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
    if request.user.role == User.Role.DOCTOR:
        patients = doctor_patient_queryset(request.user)
    if query:
        patients = patients.filter(full_name__icontains=query) | patients.filter(patient_id__icontains=query)
    return render(request, "patients/list.html", {"patients": patients, "query": query})


@login_required
@user_passes_test(can_view_patients)
@require_http_methods(["GET"])
def patient_detail(request, pk):
    patient = get_accessible_patient(request.user, pk)
    show_clinical_data = request.user.role != User.Role.RECEPTIONIST
    medical_history = patient.medical_histories.order_by("-updated_at").first() if show_clinical_data else None
    consultations = patient.consultations.select_related("doctor").all() if show_clinical_data else []
    vital_signs = patient.vital_signs.select_related("recorded_by").all() if show_clinical_data else []
    migrated_documents = (
        patient.migration_documents.select_related("batch").order_by("-created_at")
        if show_clinical_data
        else []
    )
    return render(
        request,
        "patients/detail.html",
        {
            "patient": patient,
            "medical_history": medical_history,
            "consultations": consultations,
            "vital_signs": vital_signs,
            "migrated_documents": migrated_documents,
            "show_clinical_data": show_clinical_data,
        },
    )


@login_required
@user_passes_test(can_manage_patients)
@require_http_methods(["GET", "POST"])
def update_patient(request, pk):
    patient = get_accessible_patient(request.user, pk)
    form = PatientForm(request.POST or None, instance=patient, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Patient record updated for {patient.full_name}.")
        return redirect("patient_detail", pk=patient.pk)
    return render(request, "patients/update.html", {"form": form, "patient": patient})


@login_required
@user_passes_test(can_manage_medical_records)
@require_http_methods(["GET", "POST"])
def add_medical_history(request, pk):
    patient = get_accessible_patient(request.user, pk)
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
    patient = get_accessible_patient(request.user, pk)
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
    patient = get_accessible_patient(request.user, pk)
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
@require_GET
def medical_record_history(request, pk):
    if not can_view_medical_records(request.user):
        return HttpResponseForbidden("This record is restricted to authorised clinical staff.")
    patient = get_accessible_patient(request.user, pk)
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
    patient = get_accessible_patient(request.user, pk)
    details = request.POST.get("details", "").strip()
    if not details:
        messages.error(request, "Please provide a correction note before submitting the record correction.")
        return redirect("patient_detail", pk=patient.pk)
    log_medical_record_action(patient, request.user, "clinical_record_corrected", details)
    messages.success(request, "Medical record correction noted and logged.")
    return redirect("patient_detail", pk=patient.pk)
