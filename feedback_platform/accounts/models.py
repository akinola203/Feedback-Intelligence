from django.contrib.auth.hashers import check_password, make_password
from django.db import models

from core.models import BaseModel
from organizations.models import Organization


class PlatformAdmin(BaseModel):
    """
    Operates the SaaS platform itself. Deliberately NOT related to
    Organization/User in any way — kept structurally separate so a bug
    can never accidentally grant org-level staff platform-wide reach
    (Phase 2 §A, §2).

    Real authentication wiring (login views, sessions/tokens) is Phase 3B.
    This model only owns identity + password storage for now, using
    Django's own hasher rather than a custom implementation.
    """

    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "platform_admin"

    def __str__(self):
        return self.email

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)


class User(BaseModel):
    """
    An organization member: Organization Admin, Manager, or Staff.
    Always belongs to exactly one organization for MVP (Phase 2 §4 —
    deliberate simplification, multi-org membership deferred).

    Email is unique per organization, not globally — see Phase 2 §B
    (User) and the org-scoped login decision (correction #3) for why.
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Organization Admin"
        MANAGER = "manager", "Manager"
        STAFF = "staff", "Staff"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="users"
    )
    email = models.EmailField()
    password = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "app_user"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "email"], name="uq_user_org_email"
            ),
            # Supports the composite FK from UserBranch that guarantees a
            # user can only be linked to branches within their own
            # organization (Phase 2 follow-up fix — UserBranch tenant leak).
            models.UniqueConstraint(
                fields=["id", "organization"], name="uq_user_id_org"
            ),
        ]

    def __str__(self):
        return f"{self.email} ({self.organization.slug}, {self.role})"

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)
