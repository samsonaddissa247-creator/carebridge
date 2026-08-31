from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from .models import Invoice
from .forms import InvoiceForm


@login_required
def invoice_list(request):
    invoices = Invoice.objects.select_related("patient").all()
    return render(request, "billing/list.html", {"invoices": invoices})


@login_required
def create_invoice(request):
    form = InvoiceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Invoice created.")
        return redirect("invoice_list")
    return render(request, "billing/create.html", {"form": form})


@login_required
def mark_paid(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    invoice.status = Invoice.Status.PAID
    invoice.save()
    return redirect("invoice_list")
