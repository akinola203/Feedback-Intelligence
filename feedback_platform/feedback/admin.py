from django.contrib import admin

from .models import Category, Feedback, QRCode


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_active", "created_at")
    list_filter = ("is_active", "organization")
    search_fields = ("name",)
    readonly_fields = ("created_at",)


@admin.register(QRCode)
class QRCodeAdmin(admin.ModelAdmin):
    list_display = ("token", "branch", "is_active", "revoked_at", "created_at")
    list_filter = ("is_active", "branch__organization")
    search_fields = ("token", "branch__name")
    readonly_fields = ("token", "created_at")


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "branch",
        "organization",
        "rating",
        "sentiment",
        "category",
        "source",
        "created_at",
    )
    list_filter = ("rating", "sentiment", "source", "category", "organization")
    search_fields = ("customer_email", "customer_name", "message", "branch__name")
    readonly_fields = ("organization", "sentiment", "created_at")
