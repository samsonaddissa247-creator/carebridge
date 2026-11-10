from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import User

from .reporting import (
    build_admin_dashboard_context,
    build_doctor_dashboard_context,
    build_reception_dashboard_context,
    build_reports_context,
)


@login_required
def dashboard(request):
    user = request.user
    today = timezone.localdate()

    if user.role == User.Role.ADMIN:
        return render(
            request,
            "core/dashboard_admin.html",
            build_admin_dashboard_context(today),
        )
    if user.role == User.Role.DOCTOR:
        return render(
            request,
            "core/dashboard_doctor.html",
            build_doctor_dashboard_context(user, today),
        )
    if user.role == User.Role.LAB_TECHNICIAN:
        return redirect("lab_dashboard")
    if user.role == User.Role.RECEPTIONIST:
        return render(
            request,
            "core/dashboard_reception.html",
            build_reception_dashboard_context(today),
        )
    return HttpResponseForbidden("You are not authorised to access this dashboard.")


@login_required
def reports(request):
    if request.user.role not in {
        User.Role.ADMIN,
        User.Role.DOCTOR,
        User.Role.RECEPTIONIST,
        User.Role.LAB_TECHNICIAN,
    }:
        return HttpResponseForbidden("You are not authorised to access reports.")

    date_value = request.GET.get("date", "")
    if date_value:
        try:
            selected_date = timezone.datetime.strptime(date_value, "%Y-%m-%d").date()
        except ValueError:
            return HttpResponseBadRequest("Enter a valid report date.")
    else:
        selected_date = timezone.localdate()

    return render(
        request,
        "core/reports.html",
        build_reports_context(request.user, selected_date),
    )
