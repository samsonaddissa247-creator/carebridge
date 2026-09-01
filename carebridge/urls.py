from django.conf import settings
from django.contrib import admin
from django.urls import path, re_path
from django.views.static import serve
from accounts import views as acc_views
from core import views as core_views
from patients import views as patient_views
from appointments import views as appt_views
from billing import views as bill_views

urlpatterns = [
    re_path(r"^static/(?P<path>.*)$", serve, {"document_root": settings.BASE_DIR / "static"}),
    path("django-admin/", admin.site.urls),

    # Auth
    path("", acc_views.login_view, name="login"),
    path("logout/", acc_views.logout_view, name="logout"),
    path("request-account/", acc_views.request_account, name="request_account"),
    path("staff/pending/", acc_views.pending_staff, name="pending_staff"),
    path("staff/pending/<int:user_id>/approve/", acc_views.approve_staff, name="approve_staff"),
    path("staff/pending/<int:user_id>/reject/", acc_views.reject_staff, name="reject_staff"),

    # Dashboard & reports
    path("dashboard/", core_views.dashboard, name="dashboard"),
    path("reports/", core_views.reports, name="reports"),

    # Patients
    path("patients/", patient_views.patient_list, name="patient_list"),
    path("patients/register/", patient_views.register_patient, name="register_patient"),
    path("patients/<int:pk>/", patient_views.patient_detail, name="patient_detail"),

    # Appointments
    path("appointments/", appt_views.appointment_list, name="appointment_list"),
    path("appointments/book/", appt_views.book_appointment, name="book_appointment"),
    path("appointments/<int:pk>/status/<str:new_status>/", appt_views.update_status, name="update_appointment_status"),

    # Billing
    path("billing/", bill_views.invoice_list, name="invoice_list"),
    path("billing/create/", bill_views.create_invoice, name="create_invoice"),
    path("billing/<int:pk>/paid/", bill_views.mark_paid, name="mark_paid"),
]
