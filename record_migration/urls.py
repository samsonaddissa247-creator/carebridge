from django.urls import path

from . import views

app_name = "record_migration"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("batches/create/", views.create_batch, name="create_batch"),
    path("batches/<int:batch_id>/upload/", views.upload_document, name="upload_document"),
    path("batches/<int:batch_id>/report/", views.batch_report, name="batch_report"),
    path("batches/<int:batch_id>/errors/download/", views.download_error_report, name="download_error_report"),
    path("batches/<int:batch_id>/digital/upload/", views.upload_spreadsheet, name="upload_spreadsheet"),
    path(
        "batches/<int:batch_id>/digital/files/<int:file_id>/preview/",
        views.spreadsheet_preview,
        name="spreadsheet_preview",
    ),
    path(
        "batches/<int:batch_id>/digital/files/<int:file_id>/mapping/",
        views.column_mapping,
        name="column_mapping",
    ),
    path("batches/<int:batch_id>/digital/review/", views.digital_review, name="digital_review"),
    path("batches/<int:batch_id>/digital/match/", views.run_matching, name="run_matching"),
    path(
        "batches/<int:batch_id>/digital/records/<int:record_id>/",
        views.staged_record_detail,
        name="staged_record_detail",
    ),
    path(
        "batches/<int:batch_id>/digital/files/<int:file_id>/remove/",
        views.remove_spreadsheet,
        name="remove_spreadsheet",
    ),
    path("patients/<int:patient_id>/documents/", views.patient_documents, name="patient_documents"),
    path("documents/<int:document_id>/download/", views.download_document, name="download_document"),
    path("history/", views.history, name="history"),
]
