from django.core.exceptions import ValidationError
from django.db import models

from core.managers import TenantManager
from core.models import BaseModel


class Sector(models.TextChoices):
    """Standardized supermarket operational sectors / departments."""

    GENERAL = "GENERAL", "General Store Operations"
    POS_CASHIER = "POS_CASHIER", "Front-End POS & Cashiers"
    BAKERY_PRODUCE = "BAKERY_PRODUCE", "Bakery & Fresh Produce"
    COLD_CHAIN_MEAT = "COLD_CHAIN_MEAT", "Cold Chain, Dairy & Butchery"
    GROCERY_STOCK = "GROCERY_STOCK", "Grocery, Aisles & Shelf Stocking"
    CUSTOMER_SERVICE = "CUSTOMER_SERVICE", "Customer Service & Returns"
    FACILITY_SECURITY = "FACILITY_SECURITY", "Facility, Hygiene & Security"


class Organization(BaseModel):
    """
    A supermarket company using the platform. Root of tenancy — every
    organization-scoped row in the system traces back to exactly one of
    these (Phase 2 §1-3).
    """

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "organization"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Branch(BaseModel):
    """A physical store location belonging to one organization."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="branches"
    )
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    objects = TenantManager()

    class Meta:
        db_table = "branch"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="uq_branch_org_name"
            ),
            # Supports the composite FK from Feedback/Complaint that
            # guarantees organization_id can never drift from the branch's
            # real organization (Phase 2 §D.1). Added via a manual
            # migration since Django doesn't manage composite FKs natively.
            models.UniqueConstraint(
                fields=["id", "organization"], name="uq_branch_id_org"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.organization.name})"


class UserBranch(BaseModel):
    """
    Many-to-many join between User and Branch, implementing branch-scoped
    access for Managers/Staff (Phase 2 §6). Organization Admins do not
    need rows here — their access is organization-wide by role.

    organization is denormalized from both user.organization and
    branch.organization specifically so the database can enforce that a
    User can only ever be linked to a Branch within their own
    organization — without this, UserBranch allowed a cross-org link at
    the DB level, silently defeating branch-scoped access control for
    Manager/Staff. Enforced via composite FKs in a manual migration
    (same D.1 pattern as Feedback/Complaint), not just application code.
    """

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="branch_links"
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, related_name="user_links"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="user_branch_links"
    )
    sector = models.CharField(
        max_length=40,
        choices=Sector.choices,
        default=Sector.GENERAL,
        db_index=True,
    )
    is_sector_lead = models.BooleanField(default=False)

    class Meta:
        db_table = "user_branch"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "branch"], name="uq_userbranch_user_branch"
            ),
        ]

    def __str__(self):
        return f"{self.user.email} @ {self.branch.name}"

    def clean(self):
        super().clean()
        if hasattr(self, "user") and hasattr(self, "branch"):
            if self.user.organization_id != self.branch.organization_id:
                raise ValidationError(
                    "User and Branch must belong to the same organization."
                )

    def save(self, *args, **kwargs):
        # App-layer half of the guarantee (belt-and-braces); the composite
        # FKs added in migration 0003 are the part that can't be bypassed.
        if not self.organization_id:
            self.organization_id = self.user.organization_id
        super().save(*args, **kwargs)
