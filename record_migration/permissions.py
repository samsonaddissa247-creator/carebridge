from accounts.models import User

from patients.permissions import doctor_patient_queryset


def can_view_migrations(user):
    return user.is_authenticated and user.role in {User.Role.ADMIN, User.Role.DOCTOR}


def can_access_batch(user, batch):
    if not can_view_migrations(user):
        return False
    if user.role == User.Role.ADMIN:
        return True
    return batch.created_by_id == user.pk


def accessible_batches(user):
    from .models import MigrationBatch

    batches = MigrationBatch.objects.all()
    if user.role == User.Role.DOCTOR:
        batches = batches.filter(created_by=user)
    return batches


def accessible_patients(user):
    from patients.models import Patient

    if user.role == User.Role.ADMIN:
        return Patient.objects.all()
    if user.role == User.Role.DOCTOR:
        return doctor_patient_queryset(user)
    return Patient.objects.none()
