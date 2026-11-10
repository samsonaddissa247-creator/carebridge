from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from .forms import StaffLoginForm, StaffRegistrationRequestForm
from .models import User


def is_staff_member(user):
    return user.is_authenticated and user.role in {
        User.Role.ADMIN,
        User.Role.DOCTOR,
        User.Role.RECEPTIONIST,
        User.Role.LAB_TECHNICIAN,
    }


def is_admin(user):
    return user.is_authenticated and user.role == User.Role.ADMIN


def is_front_desk_or_admin(user):
    return user.is_authenticated and user.role in {User.Role.ADMIN, User.Role.RECEPTIONIST}


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = StaffLoginForm(request, data=request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = form.get_user()
            if user.role not in {
                User.Role.ADMIN,
                User.Role.DOCTOR,
                User.Role.RECEPTIONIST,
                User.Role.LAB_TECHNICIAN,
            }:
                messages.error(request, "Your account is not authorised to access CareLink.")
            elif user.role != User.Role.ADMIN and not user.is_approved:
                messages.error(request, "Your account is still pending approval by a Hospital Administrator.")
            elif not user.is_active:
                messages.error(request, "This account is currently inactive. Please contact the Hospital Administrator.")
            else:
                auth_login(request, user)
                return redirect("dashboard")
        else:
            messages.error(request, "Incorrect ID/username or password.")
    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    auth_logout(request)
    return redirect("login")


def request_account(request):
    """Public page where a prospective staff member requests an account.
    Account is created INACTIVE and UNAPPROVED — an Administrator must approve it."""
    form = StaffRegistrationRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            "Your account request has been submitted. A Hospital Administrator must verify and "
            "approve your account before you can log in.",
        )
        return redirect("login")
    return render(request, "accounts/request_account.html", {"form": form})


@login_required
@user_passes_test(is_admin)
@require_POST
def approve_staff(request, user_id):
    staff = get_object_or_404(User, id=user_id)
    if staff.role not in {User.Role.DOCTOR, User.Role.RECEPTIONIST, User.Role.LAB_TECHNICIAN}:
        messages.error(request, "Only staff applicant accounts can be approved.")
        return redirect("pending_staff")
    staff.is_approved = True
    staff.is_active = True
    staff.save()
    messages.success(request, f"{staff.get_full_name()} has been approved and can now log in.")
    return redirect("pending_staff")


@login_required
@user_passes_test(is_admin)
@require_POST
def reject_staff(request, user_id):
    staff = get_object_or_404(User, id=user_id)
    if staff.role not in {User.Role.DOCTOR, User.Role.RECEPTIONIST, User.Role.LAB_TECHNICIAN}:
        messages.error(request, "Only pending staff accounts can be rejected.")
        return redirect("pending_staff")
    name = staff.get_full_name()
    staff.delete()
    messages.info(request, f"Request from {name} was rejected and removed.")
    return redirect("pending_staff")


@login_required
@user_passes_test(is_admin)
def pending_staff(request):
    pending = User.objects.filter(
        is_approved=False,
        role__in=[User.Role.DOCTOR, User.Role.RECEPTIONIST, User.Role.LAB_TECHNICIAN],
    )
    return render(request, "accounts/pending_staff.html", {"pending": pending})
