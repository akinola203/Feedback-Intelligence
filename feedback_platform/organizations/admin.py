from django.contrib import admin

from .models import Branch, Organization, UserBranch


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at",)


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "address", "is_active", "created_at")
    list_filter = ("is_active", "organization")
    search_fields = ("name", "address", "organization__name")
    readonly_fields = ("created_at",)


@admin.register(UserBranch)
class UserBranchAdmin(admin.ModelAdmin):
    list_display = ("user", "branch", "organization", "created_at")
    list_filter = ("organization", "branch")
    search_fields = ("user__email", "branch__name", "organization__name")
    readonly_fields = ("organization", "created_at")
