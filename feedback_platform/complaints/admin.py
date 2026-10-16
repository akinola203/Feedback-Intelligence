from django.contrib import admin

from .models import Complaint, ComplaintNote


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "organization",
        "branch",
        "status",
        "priority",
        "assigned_to",
        "created_by",
        "created_at",
    )
    list_filter = ("status", "priority", "organization", "branch")
    search_fields = (
        "resolution_summary",
        "assigned_to__email",
        "created_by__email",
        "branch__name",
    )
    readonly_fields = ("organization", "branch", "created_at")


@admin.register(ComplaintNote)
class ComplaintNoteAdmin(admin.ModelAdmin):
    list_display = ("complaint", "author", "created_at")
    list_filter = ("created_at",)
    search_fields = ("author__email", "body")
    readonly_fields = ("created_at",)
