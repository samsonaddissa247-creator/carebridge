from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from .models import Patient
from .forms import PatientForm


@login_required
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
def patient_list(request):
    query = request.GET.get("q", "")
    patients = Patient.objects.all()
    if query:
        patients = patients.filter(full_name__icontains=query) | patients.filter(patient_id__icontains=query)
    return render(request, "patients/list.html", {"patients": patients, "query": query})


@login_required
def patient_detail(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    return render(request, "patients/detail.html", {"patient": patient})
