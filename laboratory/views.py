from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.models import User

from .forms import LabRequestForm, LabResultForm
from .models import LabAuditLog, LabRequest, LabResult
from .permissions import (
    can_manage_laboratory,
    can_view_laboratory,
    doctor_can_access_patient,
    doctor_patient_queryset,
)


def role_required(permission):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not permission(request.user):
                return HttpResponseForbidden("You are not authorised to access laboratory information.")
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def visible_requests(user):
    requests = LabRequest.objects.select_related("patient", "consultation", "requested_by").prefetch_related("result")
    if user.role == User.Role.DOCTOR:
        return requests.filter(patient__in=doctor_patient_queryset(user))
    return requests


def audit(request, actor, action, *, old_status="", new_status="", details=""):
    LabAuditLog.objects.create(
        lab_request=request,
        actor=actor,
        action=action,
        old_status=old_status,
        new_status=new_status,
        details=details,
    )


@login_required
@role_required(can_view_laboratory)
@require_GET
def dashboard(request):
    requests = visible_requests(request.user)
    aggregate = requests.aggregate(
        **{
            f"status_{status.lower()}": Count("pk", filter=Q(status=status))
            for status, _label in LabRequest.Status.choices
        },
        new_today=Count("pk", filter=Q(status=LabRequest.Status.REQUESTED, created_at__date=timezone.localdate())),
        awaiting_verification=Count(
            "pk",
            filter=Q(
                status=LabRequest.Status.COMPLETED,
                result__isnull=False,
                result__verified_at__isnull=True,
            ),
        ),
    )
    context = {
        "requests": requests[:100],
        "status_counts": {
            status: aggregate[f"status_{status.lower()}"] or 0
            for status, _label in LabRequest.Status.choices
        },
        "new_today_count": aggregate["new_today"] or 0,
        "awaiting_verification_count": aggregate["awaiting_verification"] or 0,
        "can_manage": can_manage_laboratory(request.user),
        "can_create": request.user.role == User.Role.DOCTOR,
    }
    return render(request, "laboratory/dashboard.html", context)


@login_required
@role_required(lambda user: user.is_authenticated and user.role == User.Role.DOCTOR)
@require_http_methods(["GET", "POST"])
def create_request(request):
    form = LabRequestForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        lab_request = form.save(commit=False)
        lab_request.requested_by = request.user
        lab_request.save()
        audit(request=lab_request, actor=request.user, action="request_created")
        messages.success(request, "Laboratory test request created.")
        return redirect("lab_detail", pk=lab_request.pk)
    return render(request, "laboratory/request_form.html", {"form": form})


@login_required
@role_required(can_view_laboratory)
@require_GET
def request_detail(request, pk):
    lab_request = get_object_or_404(visible_requests(request.user), pk=pk)
    if request.user.role == User.Role.DOCTOR and not (
        lab_request.requested_by_id == request.user.pk
        or doctor_can_access_patient(request.user, lab_request.patient)
    ):
        return HttpResponseForbidden("You are not authorised to view this laboratory request.")
    transitions = {
        LabRequest.Status.REQUESTED: [LabRequest.Status.COLLECTED, LabRequest.Status.CANCELLED],
        LabRequest.Status.COLLECTED: [LabRequest.Status.PROCESSING, LabRequest.Status.CANCELLED],
        LabRequest.Status.PROCESSING: [LabRequest.Status.COMPLETED, LabRequest.Status.CANCELLED],
    }
    result_form = None
    if can_manage_laboratory(request.user) and lab_request.status in {
        LabRequest.Status.PROCESSING,
        LabRequest.Status.COMPLETED,
    }:
        result_form = LabResultForm(instance=getattr(lab_request, "result", None))
    return render(
        request,
        "laboratory/detail.html",
        {
            "lab_request": lab_request,
            "allowed_transitions": transitions.get(lab_request.status, []),
            "result_form": result_form,
            "can_manage": can_manage_laboratory(request.user),
        },
    )


@login_required
@role_required(can_manage_laboratory)
@require_POST
def update_status(request, pk):
    lab_request = get_object_or_404(LabRequest, pk=pk)
    new_status = request.POST.get("status", "")
    allowed = {
        LabRequest.Status.REQUESTED: {LabRequest.Status.COLLECTED, LabRequest.Status.CANCELLED},
        LabRequest.Status.COLLECTED: {LabRequest.Status.PROCESSING, LabRequest.Status.CANCELLED},
        LabRequest.Status.PROCESSING: {LabRequest.Status.COMPLETED, LabRequest.Status.CANCELLED},
    }
    if new_status not in allowed.get(lab_request.status, set()):
        messages.error(request, "That laboratory status change is not allowed.")
        return redirect("lab_detail", pk=lab_request.pk)
    if new_status == LabRequest.Status.COMPLETED and not hasattr(lab_request, "result"):
        messages.error(request, "Enter a result before completing this test.")
        return redirect("lab_detail", pk=lab_request.pk)
    old_status = lab_request.status
    lab_request.status = new_status
    lab_request.save(update_fields=["status", "updated_at"])
    audit(
        lab_request,
        request.user,
        "status_changed",
        old_status=old_status,
        new_status=new_status,
    )
    messages.success(request, f"Laboratory request marked {lab_request.get_status_display().lower()}.")
    return redirect("lab_detail", pk=lab_request.pk)


@login_required
@role_required(can_manage_laboratory)
@require_POST
def save_result(request, pk):
    lab_request = get_object_or_404(LabRequest, pk=pk)
    if lab_request.status not in {LabRequest.Status.PROCESSING, LabRequest.Status.COMPLETED}:
        messages.error(request, "Results can only be entered while processing or corrected after completion.")
        return redirect("lab_detail", pk=lab_request.pk)
    existing_result = getattr(lab_request, "result", None)
    form = LabResultForm(request.POST, instance=existing_result)
    if not form.is_valid():
        return render(
            request,
            "laboratory/detail.html",
            {
                "lab_request": lab_request,
                "allowed_transitions": [],
                "result_form": form,
                "can_manage": True,
            },
            status=400,
        )
    result = form.save(commit=False)
    result.lab_request = lab_request
    result.entered_by = request.user
    if existing_result:
        result.verified_by = None
        result.verified_at = None
    result.save()
    audit(
        lab_request,
        request.user,
        "result_corrected" if existing_result else "result_entered",
    )
    messages.success(request, "Laboratory result saved.")
    return redirect("lab_detail", pk=lab_request.pk)


@login_required
@role_required(can_manage_laboratory)
@require_POST
def verify_result(request, pk):
    lab_request = get_object_or_404(LabRequest, pk=pk, status=LabRequest.Status.COMPLETED)
    result = get_object_or_404(LabResult, lab_request=lab_request)
    if result.verified_at:
        messages.error(request, "This result has already been verified.")
        return redirect("lab_detail", pk=lab_request.pk)
    result.verified_by = request.user
    result.verified_at = timezone.now()
    result.save(update_fields=["verified_by", "verified_at"])
    audit(lab_request, request.user, "result_verified")
    messages.success(request, "Laboratory result verified.")
    return redirect("lab_detail", pk=lab_request.pk)
