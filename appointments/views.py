from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from .models import Appointment
from .forms import AppointmentForm
from accounts.models import User


@login_required
def appointment_list(request):
    appointments = Appointment.objects.select_related("patient", "doctor").all()
    if request.user.role == User.Role.DOCTOR:
        appointments = appointments.filter(doctor=request.user)
    return render(request, "appointments/list.html", {"appointments": appointments})


@login_required
def book_appointment(request):
    form = AppointmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Appointment booked.")
        return redirect("appointment_list")
    return render(request, "appointments/book.html", {"form": form})


@login_required
def update_status(request, pk, new_status):
    appt = get_object_or_404(Appointment, pk=pk)
    appt.status = new_status
    appt.save()
    return redirect("appointment_list")
