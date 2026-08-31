from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from patients.models import Patient
from appointments.models import Appointment
from billing.models import Invoice
from accounts.models import User


@login_required
def dashboard(request):
    user = request.user
    today = timezone.localdate()

    if user.role == User.Role.ADMIN:
        context = {
            "patients_total": Patient.objects.count(),
            "appointments_today": Appointment.objects.filter(scheduled_at__date=today).count(),
            "pending_appointments": Appointment.objects.filter(status="PENDING").count(),
            "pending_staff_count": User.objects.filter(is_approved=False, role__in=["DOCTOR", "RECEPTIONIST"]).count(),
            "unpaid_invoices": Invoice.objects.filter(status="UNPAID").count(),
            "recent_patients": Patient.objects.all()[:5],
        }
        return render(request, "core/dashboard_admin.html", context)

    elif user.role == User.Role.DOCTOR:
        context = {
            "my_appointments": Appointment.objects.filter(doctor=user).exclude(status="CANCELLED").order_by("scheduled_at")[:8],
            "today_count": Appointment.objects.filter(doctor=user, scheduled_at__date=today).count(),
        }
        return render(request, "core/dashboard_doctor.html", context)

    else:  # RECEPTIONIST
        context = {
            "appointments_today": Appointment.objects.filter(scheduled_at__date=today).select_related("patient", "doctor")[:8],
            "patients_total": Patient.objects.count(),
            "unpaid_invoices": Invoice.objects.filter(status="UNPAID").count(),
        }
        return render(request, "core/dashboard_reception.html", context)


@login_required
def reports(request):
    today = timezone.localdate()
    week_ago = today - timezone.timedelta(days=7)
    context = {
        "patients_total": Patient.objects.count(),
        "patients_this_week": Patient.objects.filter(registered_at__date__gte=week_ago).count(),
        "appointments_total": Appointment.objects.count(),
        "appointments_completed": Appointment.objects.filter(status="COMPLETED").count(),
        "revenue_total": sum(i.amount for i in Invoice.objects.filter(status="PAID")),
        "revenue_pending": sum(i.amount for i in Invoice.objects.filter(status="UNPAID")),
    }
    return render(request, "core/reports.html", context)
