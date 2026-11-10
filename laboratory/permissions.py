from django.db.models import Q

from accounts.models import User
from appointments.models import Appointment, QueueEntry
from patients.models import ConsultationRecord, Patient


def doctor_patient_queryset(user):
    return Patient.objects.filter(
        Q(consultations__doctor=user)
        | Q(appointments__doctor=user)
        | Q(queue_entries__assigned_doctor=user)
    ).distinct()


def doctor_can_access_patient(user, patient):
    return (
        ConsultationRecord.objects.filter(patient=patient, doctor=user).exists()
        or Appointment.objects.filter(patient=patient, doctor=user).exists()
        or QueueEntry.objects.filter(patient=patient, assigned_doctor=user).exists()
    )


def can_view_laboratory(user):
    return user.is_authenticated and user.role in {
        User.Role.ADMIN,
        User.Role.DOCTOR,
        User.Role.LAB_TECHNICIAN,
    }


def can_manage_laboratory(user):
    return user.is_authenticated and user.role == User.Role.LAB_TECHNICIAN
