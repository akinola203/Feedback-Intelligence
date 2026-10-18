from django.core.exceptions import ValidationError
from django.db import models

from core.managers import TenantManager
from core.models import BaseModel
from organizations.models import Organization


class AuditLog(BaseModel):
    """
    System-generated, append-only record of state-changing actions.
    Separate from ComplaintNote (human commentary) — see Phase 2 §10.

    Covers both organization-user actions ("John changed Complaint #217
    to In Progress") and platform-admin actions ("Platform Admin Sarah
    suspended Organization ABC") in one table (correction #5). At most
    one of actor_user / actor_platform_admin may be set; both null is
    reserved for genuinely system-generated entries.

    No update or delete path is exposed anywhere in the application for
    this model — it is written once and only ever read.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    actor_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    actor_platform_admin = models.ForeignKey(
        "accounts.PlatformAdmin",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    entity_type = models.CharField(max_length=100)
    entity_id = models.UUIDField()
    action = models.CharField(max_length=100)
    metadata = models.JSONField(null=True, blank=True)

    objects = TenantManager()

    class Meta:
        db_table = "audit_log"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~(
                    models.Q(actor_user__isnull=False)
                    & models.Q(actor_platform_admin__isnull=False)
                ),
                name="ck_auditlog_single_actor",
            ),
        ]
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["organization", "created_at"]),
        ]

    def __str__(self):
        return f"AuditLog({self.entity_type}:{self.entity_id}, {self.action})"

    def clean(self):
        super().clean()
        if self.actor_user_id and self.actor_platform_admin_id:
            raise ValidationError(
                "Audit log cannot have both an organization user and a platform admin actor."
            )
        if (
            self.actor_user_id
            and self.organization_id
            and self.actor_user.organization_id != self.organization_id
        ):
            raise ValidationError(
                "Audit log actor_user must belong to the audit log organization."
            )

    def save(self, *args, **kwargs):
        # Auto-derive organization from actor_user if not explicitly provided
        if self.actor_user_id and not self.organization_id:
            self.organization_id = self.actor_user.organization_id
        super().save(*args, **kwargs)
