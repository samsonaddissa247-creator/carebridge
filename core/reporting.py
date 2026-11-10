from datetime import datetime, time, timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts.models import User
from appointments.models import (
    Appointment,
    AppointmentAuditLog,
    QueueAuditLog,
    QueueEntry,
)
from billing.models import Invoice
from laboratory.models import LabAuditLog, LabRequest
from patients.models import ConsultationRecord, Patient


def _day_bounds(day):
    start = timezone.make_aware(datetime.combine(day, time.min))
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
    return start, end


def _period_bounds(start_day, end_day):
    start, _ = _day_bounds(start_day)
    _, end = _day_bounds(end_day)
    return start, end


def _chart_rows(rows, label_key, total_key="total"):
    max_value = max((row[total_key] for row in rows), default=0)
    return [
        {
            "label": row[label_key],
            "total": row[total_key],
            "width": round(row[total_key] * 100 / max_value) if max_value else 0,
        }
        for row in rows
    ]


def _appointment_status_rows(queryset):
    counts = queryset.values("status").annotate(total=Count("pk"))
    count_by_status = {}
    for row in counts:
        key = Appointment.Status.SCHEDULED if row["status"] == Appointment.Status.PENDING else row["status"]
        count_by_status[key] = count_by_status.get(key, 0) + row["total"]
    return [
        {
            "status": status,
            "label": label,
            "total": count_by_status.get(status, 0),
        }
        for status, label in [
            (Appointment.Status.SCHEDULED, "Scheduled"),
            (Appointment.Status.CONFIRMED, "Confirmed"),
            (Appointment.Status.COMPLETED, "Completed"),
            (Appointment.Status.CANCELLED, "Cancelled"),
        ]
    ]


def _recent_activities():
    activities = []
    activity_labels = {
        "created": "Appointment created",
        "status_update": "Appointment status updated",
        "added_to_queue": "Patient added to queue",
        "called": "Next patient called",
        "status_changed": "Queue status updated",
        "request_created": "Laboratory request created",
        "result_entered": "Laboratory result entered",
        "result_corrected": "Laboratory result corrected",
        "result_verified": "Laboratory result verified",
    }
    for log_model in (AppointmentAuditLog, QueueAuditLog, LabAuditLog):
        for log in log_model.objects.select_related("actor").order_by("-created_at")[:8]:
            activities.append(
                {
                    "label": activity_labels.get(log.action, "System activity recorded"),
                    "actor": log.actor.get_full_name() if log.actor else "Staff account",
                    "created_at": log.created_at,
                }
            )
    return sorted(activities, key=lambda activity: activity["created_at"], reverse=True)[:8]


def build_admin_dashboard_context(today):
    start, end = _day_bounds(today)
    appointments_today = Appointment.objects.filter(scheduled_at__gte=start, scheduled_at__lt=end)
    queue_today = QueueEntry.objects.filter(added_at__gte=start, added_at__lt=end)
    lab_requests = LabRequest.objects.all()
    status_rows = _appointment_status_rows(appointments_today)
    chart_max = max((row["total"] for row in status_rows), default=0)
    for row in status_rows:
        row["width"] = round(row["total"] * 100 / chart_max) if chart_max else 0

    return {
        "today": today,
        "patients_total": Patient.objects.count(),
        "appointments_today": appointments_today.exclude(status=Appointment.Status.CANCELLED).count(),
        "completed_appointments_today": appointments_today.filter(status=Appointment.Status.COMPLETED).count(),
        "cancelled_appointments_today": appointments_today.filter(status=Appointment.Status.CANCELLED).count(),
        "patients_waiting": queue_today.filter(status=QueueEntry.Status.WAITING).count(),
        "patients_in_progress": queue_today.filter(status=QueueEntry.Status.IN_PROGRESS).count(),
        "pending_lab_requests": lab_requests.filter(
            status__in=[
                LabRequest.Status.REQUESTED,
                LabRequest.Status.COLLECTED,
                LabRequest.Status.PROCESSING,
            ]
        ).count(),
        "completed_lab_requests": lab_requests.filter(
            status=LabRequest.Status.COMPLETED,
            updated_at__gte=start,
            updated_at__lt=end,
        ).count(),
        "pending_staff_count": User.objects.filter(
            is_approved=False,
            role__in=[User.Role.DOCTOR, User.Role.RECEPTIONIST, User.Role.LAB_TECHNICIAN],
        ).count(),
        "unpaid_invoices": Invoice.objects.filter(status=Invoice.Status.UNPAID).count(),
        "recent_activities": _recent_activities(),
        "appointment_status_rows": status_rows,
        "recent_patients": Patient.objects.only("id", "full_name", "patient_id", "registered_at").order_by("-registered_at")[:5],
    }


def build_reception_dashboard_context(today):
    start, end = _day_bounds(today)
    appointments_today = (
        Appointment.objects.filter(scheduled_at__gte=start, scheduled_at__lt=end)
        .select_related("patient", "doctor")
        .order_by("scheduled_at")
    )
    upcoming_appointments = (
        Appointment.objects.filter(scheduled_at__gte=end)
        .exclude(status__in=[Appointment.Status.CANCELLED, Appointment.Status.COMPLETED])
        .select_related("patient", "doctor")
        .order_by("scheduled_at")[:8]
    )
    queue_today = QueueEntry.objects.filter(added_at__gte=start, added_at__lt=end)
    return {
        "patients_total": Patient.objects.count(),
        "registered_today": Patient.objects.filter(registered_at__gte=start, registered_at__lt=end).count(),
        "appointments_today": appointments_today[:8],
        "upcoming_appointments": upcoming_appointments,
        "appointments_today_count": appointments_today.count(),
        "waiting_queue": queue_today.filter(status=QueueEntry.Status.WAITING)
        .select_related("patient", "assigned_doctor")
        .order_by("added_at")[:8],
        "waiting_count": queue_today.filter(status=QueueEntry.Status.WAITING).count(),
        "in_progress_count": queue_today.filter(status=QueueEntry.Status.IN_PROGRESS).count(),
        "completed_queue_count": queue_today.filter(status=QueueEntry.Status.COMPLETED).count(),
        "unpaid_invoices": Invoice.objects.filter(status=Invoice.Status.UNPAID).count(),
    }


def build_doctor_dashboard_context(user, today):
    start, end = _day_bounds(today)
    appointments = Appointment.objects.filter(doctor=user).select_related("patient")
    appointments_today = appointments.filter(scheduled_at__gte=start, scheduled_at__lt=end)
    upcoming_appointments = (
        appointments.filter(scheduled_at__gte=end)
        .exclude(status__in=[Appointment.Status.CANCELLED, Appointment.Status.COMPLETED])
        .order_by("scheduled_at")[:8]
    )
    queue_today = QueueEntry.objects.filter(
        assigned_doctor=user,
        added_at__gte=start,
        added_at__lt=end,
    )
    assigned_patients = Patient.objects.filter(
        Q(appointments__doctor=user) | Q(queue_entries__assigned_doctor=user)
    ).distinct().order_by("full_name")[:8]
    pending_lab_review = LabRequest.objects.filter(
        requested_by=user,
        status=LabRequest.Status.COMPLETED,
        result__isnull=False,
        result__verified_at__isnull=True,
    ).count()
    completed_consultations_today = ConsultationRecord.objects.filter(
        doctor=user,
        consultation_datetime__gte=start,
        consultation_datetime__lt=end,
    ).count()
    status_rows = _appointment_status_rows(appointments_today)
    chart_max = max((row["total"] for row in status_rows), default=0)
    for row in status_rows:
        row["width"] = round(row["total"] * 100 / chart_max) if chart_max else 0

    return {
        "appointments_today": appointments_today.select_related("patient").order_by("scheduled_at"),
        "today_count": appointments_today.exclude(status=Appointment.Status.CANCELLED).count(),
        "upcoming_appointments": upcoming_appointments,
        "assigned_patients": assigned_patients,
        "waiting_queue": queue_today.filter(status=QueueEntry.Status.WAITING)
        .select_related("patient")
        .order_by("added_at"),
        "waiting_count": queue_today.filter(status=QueueEntry.Status.WAITING).count(),
        "in_progress_count": queue_today.filter(status=QueueEntry.Status.IN_PROGRESS).count(),
        "completed_consultations_today": completed_consultations_today,
        "pending_lab_review": pending_lab_review,
        "appointment_status_rows": status_rows,
    }


def _daily_chart_data(queryset, field, start_day, end_day):
    start, end = _period_bounds(start_day, end_day)
    records = (
        queryset.filter(**{f"{field}__gte": start, f"{field}__lt": end})
        .annotate(report_day=TruncDate(field))
        .values("report_day")
        .annotate(total=Count("pk"))
        .order_by("report_day")
    )
    count_by_day = {row["report_day"]: row["total"] for row in records}
    days = []
    day = start_day
    while day <= end_day:
        days.append({"report_day": day, "total": count_by_day.get(day, 0)})
        day += timedelta(days=1)
    return _chart_rows(days, "report_day")


def build_reports_context(user, selected_date):
    week_start = selected_date - timedelta(days=selected_date.weekday())
    week_end = week_start + timedelta(days=6)
    month_start = selected_date.replace(day=1)
    if selected_date.month == 12:
        next_month = selected_date.replace(year=selected_date.year + 1, month=1, day=1)
    else:
        next_month = selected_date.replace(month=selected_date.month + 1, day=1)
    month_end = next_month - timedelta(days=1)
    day_start, day_end = _day_bounds(selected_date)
    week_start_dt, week_end_dt = _period_bounds(week_start, week_end)
    month_start_dt, month_end_dt = _period_bounds(month_start, month_end)

    can_view_admin_reports = user.role == User.Role.ADMIN
    can_view_reception_reports = user.role in {User.Role.ADMIN, User.Role.RECEPTIONIST}
    can_view_doctor_reports = user.role == User.Role.DOCTOR
    can_view_lab_reports = user.role in {User.Role.ADMIN, User.Role.LAB_TECHNICIAN}

    context = {
        "selected_date": selected_date,
        "can_view_admin_reports": can_view_admin_reports,
        "can_view_reception_reports": can_view_reception_reports,
        "can_view_doctor_reports": can_view_doctor_reports,
        "can_view_lab_reports": can_view_lab_reports,
    }
    if can_view_admin_reports or can_view_reception_reports or can_view_doctor_reports:
        appointments = Appointment.objects.all()
        if can_view_doctor_reports:
            appointments = appointments.filter(doctor=user)
        daily = appointments.filter(scheduled_at__gte=day_start, scheduled_at__lt=day_end)
        weekly = appointments.filter(scheduled_at__gte=week_start_dt, scheduled_at__lt=week_end_dt)
        monthly = appointments.filter(scheduled_at__gte=month_start_dt, scheduled_at__lt=month_end_dt)
        context.update(
            daily_appointments=_appointment_status_rows(daily),
            daily_appointments_total=daily.count(),
            weekly_appointments_total=weekly.count(),
            monthly_appointments_total=monthly.count(),
            weekly_appointment_chart=_daily_chart_data(appointments, "scheduled_at", week_start, week_end),
            monthly_appointment_chart=_daily_chart_data(appointments, "scheduled_at", month_start, month_end),
        )

    if can_view_admin_reports or can_view_reception_reports:
        queue = QueueEntry.objects.filter(added_at__gte=day_start, added_at__lt=day_end)
        registration_queryset = Patient.objects.filter(registered_at__gte=day_start, registered_at__lt=day_end)
        not_cancelled = queue.exclude(status=QueueEntry.Status.CANCELLED)
        completed_count = queue.filter(status=QueueEntry.Status.COMPLETED).count()
        throughput_denominator = not_cancelled.count()
        context.update(
            queue_total=queue.count(),
            queue_waiting=queue.filter(status=QueueEntry.Status.WAITING).count(),
            queue_in_progress=queue.filter(status=QueueEntry.Status.IN_PROGRESS).count(),
            queue_completed=completed_count,
            queue_cancelled=queue.filter(status=QueueEntry.Status.CANCELLED).count(),
            queue_completion_percent=round(completed_count * 100 / throughput_denominator)
            if throughput_denominator
            else 0,
            patient_registrations=registration_queryset.count(),
            patients_total=Patient.objects.count(),
            patient_registration_chart=_daily_chart_data(
                Patient.objects.all(),
                "registered_at",
                week_start,
                week_end,
            ),
        )

    if can_view_lab_reports:
        labs = LabRequest.objects.filter(created_at__gte=day_start, created_at__lt=day_end)
        lab_status_counts = labs.values("status").annotate(total=Count("pk"))
        lab_counts = {row["status"]: row["total"] for row in lab_status_counts}
        lab_rows = [
            {"label": label, "total": lab_counts.get(status, 0)}
            for status, label in LabRequest.Status.choices
        ]
        maximum = max((row["total"] for row in lab_rows), default=0)
        for row in lab_rows:
            row["width"] = round(row["total"] * 100 / maximum) if maximum else 0
        context.update(
            lab_requests_total=labs.count(),
            lab_requests_pending=labs.filter(
                status__in=[
                    LabRequest.Status.REQUESTED,
                    LabRequest.Status.COLLECTED,
                    LabRequest.Status.PROCESSING,
                ]
            ).count(),
            lab_requests_completed=labs.filter(status=LabRequest.Status.COMPLETED).count(),
            lab_status_rows=lab_rows,
        )
    elif can_view_doctor_reports:
        doctor_labs = LabRequest.objects.filter(
            requested_by=user,
            created_at__gte=day_start,
            created_at__lt=day_end,
        )
        doctor_consultations = ConsultationRecord.objects.filter(doctor=user)
        context.update(
            lab_requests_pending=doctor_labs.filter(
                status__in=[
                    LabRequest.Status.REQUESTED,
                    LabRequest.Status.COLLECTED,
                    LabRequest.Status.PROCESSING,
                ]
            ).count(),
            lab_results_awaiting_review=doctor_labs.filter(
                status=LabRequest.Status.COMPLETED,
                result__isnull=False,
                result__verified_at__isnull=True,
            ).count(),
            consultations_on_date=doctor_consultations.filter(
                consultation_datetime__gte=day_start,
                consultation_datetime__lt=day_end,
            ).count(),
            consultations_this_week=doctor_consultations.filter(
                consultation_datetime__gte=week_start_dt,
                consultation_datetime__lt=week_end_dt,
            ).count(),
            consultations_this_month=doctor_consultations.filter(
                consultation_datetime__gte=month_start_dt,
                consultation_datetime__lt=month_end_dt,
            ).count(),
        )

    if can_view_admin_reports:
        weekly_registration_start, weekly_registration_end = _period_bounds(week_start, week_end)
        context.update(
            patients_total=Patient.objects.count(),
            registrations_this_week=Patient.objects.filter(
                registered_at__gte=weekly_registration_start,
                registered_at__lt=weekly_registration_end,
            ).count(),
            appointments_total=Appointment.objects.count(),
            revenue_total=Invoice.objects.filter(status=Invoice.Status.PAID).aggregate(total=Sum("amount"))["total"] or 0,
            revenue_pending=Invoice.objects.filter(status=Invoice.Status.UNPAID).aggregate(total=Sum("amount"))["total"] or 0,
        )

    return context
