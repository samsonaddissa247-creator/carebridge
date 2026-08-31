from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from .forms import StaffLoginForm, StaffRegistrationRequestForm
from .models import User


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = StaffLoginForm(request, data=request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = form.get_user()
            if user.role != User.Role.ADMIN and not user.is_approved:
                messages.error(request, "Your account is still pending approval by a Hospital Administrator.")
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


def is_admin(user):
    return user.is_authenticated and user.role == User.Role.ADMIN


@login_required
@user_passes_test(is_admin)
def pending_staff(request):
    pending = User.objects.filter(is_approved=False, role__in=[User.Role.DOCTOR, User.Role.RECEPTIONIST])
    return render(request, "accounts/pending_staff.html", {"pending": pending})


@login_required
@user_passes_test(is_admin)
def approve_staff(request, user_id):
    staff = get_object_or_404(User, id=user_id)
    staff.is_approved = True
    staff.is_active = True
    staff.save()
    messages.success(request, f"{staff.get_full_name()} has been approved and can now log in.")
    return redirect("pending_staff")


@login_required
@user_passes_test(is_admin)
def reject_staff(request, user_id):
    staff = get_object_or_404(User, id=user_id)
    name = staff.get_full_name()
    staff.delete()
    messages.info(request, f"Request from {name} was rejected and removed.")
    return redirect("pending_staff")
