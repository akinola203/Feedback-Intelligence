from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "entity_type",
        "entity_id",
        "action",
        "organization",
        "actor_user",
        "actor_platform_admin",
        "created_at",
    )
    list_filter = ("entity_type", "action", "created_at", "organization")
    search_fields = (
        "entity_type",
        "action",
        "actor_user__email",
        "actor_platform_admin__email",
    )
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
