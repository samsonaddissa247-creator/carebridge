from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST
from .models import Invoice
from .forms import InvoiceForm
from accounts.models import User


def is_front_desk_or_admin(user):
    return user.is_authenticated and user.role in {User.Role.ADMIN, User.Role.RECEPTIONIST}


@login_required
@user_passes_test(is_front_desk_or_admin)
@require_http_methods(["GET"])
def invoice_list(request):
    invoices = Invoice.objects.select_related("patient").all()
    return render(request, "billing/list.html", {"invoices": invoices})


@login_required
@user_passes_test(is_front_desk_or_admin)
@require_http_methods(["GET", "POST"])
def create_invoice(request):
    form = InvoiceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Invoice created.")
        return redirect("invoice_list")
    return render(request, "billing/create.html", {"form": form})


@login_required
@user_passes_test(is_front_desk_or_admin)
@require_POST
def mark_paid(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    invoice.status = Invoice.Status.PAID
    invoice.save()
    messages.success(request, "Invoice marked as paid.")
    return redirect("invoice_list")
