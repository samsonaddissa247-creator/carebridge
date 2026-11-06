from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from .models import Appointment, AppointmentAuditLog, QueueEntry, QueueAuditLog
from .forms import AppointmentForm, QueueEntryForm
from accounts.models import User


def is_staff_member(user):
    return user.is_authenticated and user.role in {User.Role.ADMIN, User.Role.DOCTOR, User.Role.RECEPTIONIST}


def can_manage_appointments(user):
    return user.is_authenticated and user.role in {User.Role.ADMIN, User.Role.RECEPTIONIST}


def can_view_appointments(user):
    return user.is_authenticated and user.role in {User.Role.ADMIN, User.Role.DOCTOR, User.Role.RECEPTIONIST}


def can_manage_queue(user):
    return user.is_authenticated and user.role in {User.Role.ADMIN, User.Role.RECEPTIONIST}


def can_view_queue(user):
    return user.is_authenticated and user.role in {User.Role.ADMIN, User.Role.DOCTOR, User.Role.RECEPTIONIST}


def log_appointment_change(appointment, actor, action, old_status, new_status, details=""):
    AppointmentAuditLog.objects.create(
        appointment=appointment,
        actor=actor,
        action=action,
        old_status=old_status or "",
        new_status=new_status or "",
        details=details,
    )


def log_queue_change(queue_entry, actor, action, old_status, new_status, details=""):
    QueueAuditLog.objects.create(
        queue_entry=queue_entry,
        actor=actor,
        action=action,
        old_status=old_status or "",
        new_status=new_status or "",
        details=details,
    )


@login_required
@user_passes_test(can_view_appointments)
@require_http_methods(["GET"])
def appointment_list(request):
    appointments = Appointment.objects.select_related("patient", "doctor").all()
    if request.user.role == User.Role.DOCTOR:
        appointments = appointments.filter(doctor=request.user)
    return render(request, "appointments/list.html", {"appointments": appointments})


@login_required
@user_passes_test(can_manage_appointments)
@require_http_methods(["GET", "POST"])
def book_appointment(request):
    form = AppointmentForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            existing = Appointment.objects.filter(
                patient=form.cleaned_data["patient"],
                doctor=form.cleaned_data["doctor"],
                scheduled_at=form.cleaned_data["scheduled_at"],
            ).exists()
            if existing:
                messages.error(request, "This appointment already exists for the same patient, doctor and date/time.")
            else:
                appointment = form.save(commit=False)
                appointment.status = Appointment.Status.SCHEDULED
                appointment.save()
                log_appointment_change(
                    appointment,
                    request.user,
                    "created",
                    "",
                    Appointment.Status.SCHEDULED,
                    f"Booked for {appointment.patient.full_name}",
                )
                messages.success(request, "Appointment booked.")
                return redirect("appointment_list")
    return render(request, "appointments/book.html", {"form": form})


@login_required
@user_passes_test(can_view_appointments)
@require_POST
def update_status(request, pk, new_status):
    if new_status not in {status.value for status in Appointment.Status}:
        messages.error(request, "Invalid appointment status selected.")
        return redirect("appointment_list")

    appt = get_object_or_404(Appointment, pk=pk)
    if request.user.role == User.Role.DOCTOR and appt.doctor_id != request.user.id:
        messages.error(request, "You can only update your own appointment status.")
        return redirect("appointment_list")

    old_status = appt.status
    if new_status == Appointment.Status.CANCELLED and not request.POST.get("cancel_reason", "").strip():
        messages.error(request, "A reason is required when cancelling an appointment.")
        return redirect("appointment_list")

    appt.status = new_status
    if new_status == Appointment.Status.CANCELLED:
        appt.reason = request.POST.get("cancel_reason", appt.reason).strip() or appt.reason
        appt.notes = (appt.notes or "") + "\nCancellation reason: " + request.POST.get("cancel_reason", "").strip()
    appt.save()

    log_appointment_change(
        appt,
        request.user,
        "status_update",
        old_status,
        new_status,
        f"Updated status from {old_status} to {new_status}",
    )
    messages.success(request, "Appointment status updated.")
    return redirect("appointment_list")


@login_required
@user_passes_test(can_view_queue)
@require_http_methods(["GET"])
def queue_dashboard(request):
    today = timezone.localdate()
    queue_entries = QueueEntry.objects.select_related("patient", "appointment", "assigned_doctor", "added_by").filter(
        added_at__date=today
    )

    if request.user.role == User.Role.DOCTOR:
        queue_entries = queue_entries.filter(
            assigned_doctor=request.user
        )

    waiting = queue_entries.filter(status=QueueEntry.Status.WAITING).count()
    in_progress = queue_entries.filter(status=QueueEntry.Status.IN_PROGRESS).count()
    completed = queue_entries.filter(status=QueueEntry.Status.COMPLETED).count()
    total_today = queue_entries.count()
    context = {
        "queue_entries": queue_entries,
        "total_today": total_today,
        "waiting_count": waiting,
        "in_progress_count": in_progress,
        "completed_count": completed,
    }
    return render(request, "appointments/queue_dashboard.html", context)


@login_required
@user_passes_test(can_manage_queue)
@require_http_methods(["GET", "POST"])
def add_to_queue(request):
    form = QueueEntryForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        active = QueueEntry.objects.filter(patient=form.cleaned_data["patient"]).filter(
            status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.CALLED, QueueEntry.Status.IN_PROGRESS]
        ).exists()
        if active:
            messages.error(request, "This patient already has an active queue entry for the current visit.")
        else:
            queue_entry = form.save(commit=False)
            queue_entry.added_by = request.user
            queue_entry.queue_number = QueueEntry.generate_queue_number()
            queue_entry.status = QueueEntry.Status.WAITING
            queue_entry.save()
            log_queue_change(
                queue_entry,
                request.user,
                "added_to_queue",
                "",
                QueueEntry.Status.WAITING,
                f"Queue number assigned: {queue_entry.queue_number}",
            )
            messages.success(request, f"Patient added to the queue with number {queue_entry.queue_number}.")
            return redirect("queue_dashboard")
    return render(request, "appointments/add_to_queue.html", {"form": form})


@login_required
@user_passes_test(can_view_queue)
@require_POST
def call_next_patient(request):
    if not can_manage_queue(request.user):
        messages.error(request, "You are not permitted to call the next patient.")
        return redirect("queue_dashboard")

    next_entry = QueueEntry.objects.filter(status=QueueEntry.Status.WAITING).order_by("queue_number").first()
    if not next_entry:
        messages.info(request, "There is no waiting patient in the queue.")
        return redirect("queue_dashboard")

    old_status = next_entry.status
    next_entry.status = QueueEntry.Status.CALLED
    next_entry.called_at = timezone.now()
    next_entry.save()
    log_queue_change(
        next_entry,
        request.user,
        "called",
        old_status,
        QueueEntry.Status.CALLED,
        "Called next patient in queue",
    )
    messages.success(request, f"Called patient {next_entry.patient.full_name} ({next_entry.queue_number}).")
    return redirect("queue_dashboard")


@login_required
@user_passes_test(can_view_queue)
@require_POST
def update_queue_status(request, pk, new_status):
    if new_status not in {status.value for status in QueueEntry.Status}:
        messages.error(request, "Invalid queue status selected.")
        return redirect("queue_dashboard")

    queue_entry = get_object_or_404(QueueEntry, pk=pk)
    if request.user.role == User.Role.DOCTOR and queue_entry.assigned_doctor_id != request.user.id:
        messages.error(request, "You can only update your assigned patients.")
        return redirect("queue_dashboard")

    if request.user.role not in {User.Role.ADMIN, User.Role.RECEPTIONIST} and request.user.role == User.Role.DOCTOR and new_status not in {QueueEntry.Status.CALLED, QueueEntry.Status.IN_PROGRESS, QueueEntry.Status.COMPLETED}:
        messages.error(request, "You are only allowed to update doctors' workflow statuses.")
        return redirect("queue_dashboard")

    old_status = queue_entry.status
    queue_entry.status = new_status
    if new_status == QueueEntry.Status.COMPLETED:
        queue_entry.completed_at = timezone.now()
    elif new_status in {QueueEntry.Status.WAITING, QueueEntry.Status.CALLED, QueueEntry.Status.IN_PROGRESS}:
        queue_entry.completed_at = None
    if new_status == QueueEntry.Status.CALLED:
        queue_entry.called_at = timezone.now()
    queue_entry.save()
    log_queue_change(
        queue_entry,
        request.user,
        "status_update",
        old_status,
        new_status,
        f"Status changed from {old_status} to {new_status}",
    )
    messages.success(request, "Queue status updated.")
    return redirect("queue_dashboard")
