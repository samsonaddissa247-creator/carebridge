from django.apps import AppConfig


class RecordMigrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "record_migration"
    verbose_name = "Patient records migration"
