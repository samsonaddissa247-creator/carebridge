from django.db.models import Q

from accounts.models import User

from .models import Patient


def doctor_patient_queryset(user):
    if not user.is_authenticated or user.role != User.Role.DOCTOR:
        return Patient.objects.none()
    return Patient.objects.filter(
        Q(consultations__doctor=user)
        | Q(appointments__doctor=user)
        | Q(queue_entries__assigned_doctor=user)
    ).distinct()


def doctor_can_access_patient(user, patient):
    return doctor_patient_queryset(user).filter(pk=patient.pk).exists()
