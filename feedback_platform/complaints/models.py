from django.core.exceptions import ValidationError
from django.db import models

from core.managers import TenantManager
from core.models import BaseModel
from feedback.models import Feedback
from organizations.models import Branch, Organization


class Complaint(BaseModel):
    """
    The actionable escalation of a Feedback. Zero-or-one per feedback,
    enforced by the OneToOne field below (Phase 2 §7-8). Created
    manually by a Manager/Admin — never automatically (Phase 2 §8).

    organization and branch are denormalized from feedback for direct
    tenant/branch filtering; both are protected by composite FKs added
    in a manual migration (Phase 2 §D.1), so a mismatch is rejected by
    the database itself, not just application code.
    """

    class Status(models.TextChoices):
        NEW = "new", "New"
        REVIEWED = "reviewed", "Reviewed"
        IN_PROGRESS = "in_progress", "In Progress"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    feedback = models.OneToOneField(
        Feedback, on_delete=models.PROTECT, related_name="complaint"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="complaints"
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name="complaints"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NEW
    )
    priority = models.CharField(
        max_length=20, choices=Priority.choices, default=Priority.MEDIUM
    )
    assigned_to = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_complaints",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="created_complaints",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_summary = models.TextField(blank=True, null=True)

    objects = TenantManager()

    class Meta:
        db_table = "complaint"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["assigned_to"]),
            models.Index(fields=["branch"]),
        ]

    def __str__(self):
        return f"Complaint({self.id}, {self.status})"

    def clean(self):
        super().clean()
        if (
            self.feedback_id
            and self.branch_id
            and self.feedback.branch_id != self.branch_id
        ):
            raise ValidationError(
                "Complaint branch must match the parent feedback branch."
            )
        if (
            self.branch_id
            and self.organization_id
            and self.branch.organization_id != self.organization_id
        ):
            raise ValidationError(
                "Complaint organization must match the branch organization."
            )
        if (
            self.created_by_id
            and self.organization_id
            and self.created_by.organization_id != self.organization_id
        ):
            raise ValidationError(
                "Complaint creator must belong to the complaint organization."
            )
        if (
            self.assigned_to_id
            and self.organization_id
            and self.assigned_to.organization_id != self.organization_id
        ):
            raise ValidationError(
                "Assigned user must belong to the complaint organization."
            )
        if (
            self.assigned_to_id
            and self.branch_id
            and self.assigned_to.role != "admin"
        ):
            from organizations.models import UserBranch
            if not UserBranch.objects.filter(user_id=self.assigned_to_id, branch_id=self.branch_id).exists():
                raise ValidationError(
                    "Assigned user must be linked to the complaint branch."
                )

    def save(self, *args, **kwargs):
        # Belt-and-braces app-layer consistency, mirroring Feedback.save()
        # (Phase 2 §D.1) — the DB composite FKs are the hard guarantee.
        if self.feedback_id and not self.branch_id:
            self.branch_id = self.feedback.branch_id
        if self.branch_id and not self.organization_id:
            self.organization_id = self.branch.organization_id
        elif self.feedback_id and not self.organization_id:
            self.organization_id = self.feedback.organization_id
        super().save(*args, **kwargs)


class ComplaintNote(BaseModel):
    """Human-authored internal commentary on a complaint (Phase 2 §10)."""

    complaint = models.ForeignKey(
        Complaint, on_delete=models.CASCADE, related_name="notes"
    )
    author = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    body = models.TextField()

    class Meta:
        db_table = "complaint_note"
        ordering = ["created_at"]

    def __str__(self):
        return f"Note on {self.complaint_id} by {self.author_id}"

    def clean(self):
        super().clean()
        if (
            self.author_id
            and self.complaint_id
            and self.author.organization_id != self.complaint.organization_id
        ):
            raise ValidationError(
                "Note author must belong to the same organization as the complaint."
            )
