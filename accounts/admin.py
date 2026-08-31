from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CareBridgeUserAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "role", "staff_id", "is_approved", "is_active")
    list_filter = ("role", "is_approved", "is_active")
    fieldsets = UserAdmin.fieldsets + (
        ("CareBridge role & verification", {
            "fields": ("role", "staff_id", "department", "is_approved")
        }),
    )
