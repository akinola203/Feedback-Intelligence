from django.contrib import admin

from .models import PlatformAdmin, User


@admin.register(PlatformAdmin)
class PlatformAdminAdmin(admin.ModelAdmin):
    list_display = ("email", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("email",)
    readonly_fields = ("password", "created_at")


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "full_name", "organization", "role", "is_staff", "is_superuser", "is_active", "created_at")
    list_filter = ("role", "is_staff", "is_superuser", "is_active", "organization")
    search_fields = ("email", "full_name", "organization__name", "organization__slug")
    readonly_fields = ("password", "last_login", "created_at")
