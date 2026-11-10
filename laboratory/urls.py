from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="lab_dashboard"),
    path("requests/new/", views.create_request, name="lab_create_request"),
    path("requests/<int:pk>/", views.request_detail, name="lab_detail"),
    path("requests/<int:pk>/status/", views.update_status, name="lab_update_status"),
    path("requests/<int:pk>/result/", views.save_result, name="lab_save_result"),
    path("requests/<int:pk>/verify/", views.verify_result, name="lab_verify_result"),
]
