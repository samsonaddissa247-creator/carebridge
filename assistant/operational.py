from django.utils import timezone

from accounts.models import User
from appointments.models import Appointment, QueueEntry
from laboratory.models import LabRequest
from patients.models import ConsultationRecord, Patient


def build_operational_summary(user):
    """Return role-scoped counts only; never include individual patient details."""
    today = timezone.localdate()
    data = {"date": today.isoformat(), "role": user.get_role_display()}

    if user.role == User.Role.ADMIN:
        appointments = Appointment.objects.filter(scheduled_at__date=today)
        queue = QueueEntry.objects.filter(added_at__date=today)
        labs = LabRequest.objects.all()
        data.update(
            registered_patient_total=Patient.objects.count(),
            appointments_scheduled_today=appointments.exclude(status=Appointment.Status.CANCELLED).count(),
            appointments_completed_today=appointments.filter(status=Appointment.Status.COMPLETED).count(),
            appointments_cancelled_today=appointments.filter(status=Appointment.Status.CANCELLED).count(),
            patients_waiting_today=queue.filter(status=QueueEntry.Status.WAITING).count(),
            patients_in_progress_today=queue.filter(status=QueueEntry.Status.IN_PROGRESS).count(),
            laboratory_requests_pending=labs.filter(
                status__in=[
                    LabRequest.Status.REQUESTED,
                    LabRequest.Status.COLLECTED,
                    LabRequest.Status.PROCESSING,
                ]
            ).count(),
            laboratory_requests_processing=labs.filter(status=LabRequest.Status.PROCESSING).count(),
        )
    elif user.role == User.Role.RECEPTIONIST:
        appointments = Appointment.objects.filter(scheduled_at__date=today)
        queue = QueueEntry.objects.filter(added_at__date=today)
        data.update(
            registered_patients_total=Patient.objects.count(),
            patients_registered_today=Patient.objects.filter(registered_at__date=today).count(),
            appointments_scheduled_today=appointments.exclude(status=Appointment.Status.CANCELLED).count(),
            appointments_completed_today=appointments.filter(status=Appointment.Status.COMPLETED).count(),
            appointments_cancelled_today=appointments.filter(status=Appointment.Status.CANCELLED).count(),
            patients_waiting_today=queue.filter(status=QueueEntry.Status.WAITING).count(),
            patients_in_progress_today=queue.filter(status=QueueEntry.Status.IN_PROGRESS).count(),
            patients_completed_today=queue.filter(status=QueueEntry.Status.COMPLETED).count(),
        )
    elif user.role == User.Role.DOCTOR:
        appointments = Appointment.objects.filter(doctor=user, scheduled_at__date=today)
        queue = QueueEntry.objects.filter(assigned_doctor=user, added_at__date=today)
        labs = LabRequest.objects.filter(requested_by=user)
        data.update(
            my_appointments_scheduled_today=appointments.exclude(status=Appointment.Status.CANCELLED).count(),
            my_appointments_completed_today=appointments.filter(status=Appointment.Status.COMPLETED).count(),
            my_appointments_cancelled_today=appointments.filter(status=Appointment.Status.CANCELLED).count(),
            my_patients_waiting_today=queue.filter(status=QueueEntry.Status.WAITING).count(),
            my_patients_in_progress_today=queue.filter(status=QueueEntry.Status.IN_PROGRESS).count(),
            my_consultations_today=ConsultationRecord.objects.filter(
                doctor=user,
                consultation_datetime__date=today,
            )
            .count(),
            my_lab_requests_pending=labs.filter(
                status__in=[LabRequest.Status.REQUESTED, LabRequest.Status.COLLECTED, LabRequest.Status.PROCESSING]
            ).count(),
            my_lab_requests_completed_today=labs.filter(
                status=LabRequest.Status.COMPLETED,
                updated_at__date=today,
            ).count(),
            my_lab_results_awaiting_review=labs.filter(
                status=LabRequest.Status.COMPLETED,
                result__isnull=False,
                result__verified_at__isnull=True,
            ).count(),
        )
    elif user.role == User.Role.LAB_TECHNICIAN:
        labs = LabRequest.objects.all()
        data.update(
            laboratory_requests_new=labs.filter(status=LabRequest.Status.REQUESTED).count(),
            laboratory_requests_collected=labs.filter(status=LabRequest.Status.COLLECTED).count(),
            laboratory_requests_processing=labs.filter(status=LabRequest.Status.PROCESSING).count(),
            laboratory_results_awaiting_verification=LabRequest.objects.filter(
                status=LabRequest.Status.COMPLETED,
                result__isnull=False,
                result__verified_at__isnull=True,
            ).count(),
            laboratory_requests_completed_today=labs.filter(
                status=LabRequest.Status.COMPLETED,
                updated_at__date=today,
            ).count(),
            laboratory_requests_cancelled=labs.filter(status=LabRequest.Status.CANCELLED).count(),
        )
    else:
        raise ValueError("This staff role does not have access to the assistant.")

    return data
