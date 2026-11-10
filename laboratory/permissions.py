from accounts.models import User
from patients.permissions import doctor_can_access_patient, doctor_patient_queryset


def can_view_laboratory(user):
    return user.is_authenticated and user.role in {
        User.Role.ADMIN,
        User.Role.DOCTOR,
        User.Role.LAB_TECHNICIAN,
    }


def can_manage_laboratory(user):
    return user.is_authenticated and user.role == User.Role.LAB_TECHNICIAN
