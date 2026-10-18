import secrets

from django.core.exceptions import ValidationError
from django.db import models

from core.managers import TenantManager
from core.models import BaseModel
from organizations.models import Branch, Organization


class Category(BaseModel):
    """
    Feedback category. Platform-defined in MVP (Phase 2 correction #1):
    organization is nullable for future extensibility only — every row
    created by the MVP seed data has organization=None, and there is no
    application code path (API, admin action, permission) that creates a
    non-null row yet. Organization-specific categories remain deferred.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="categories",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "category"
        ordering = ["name"]
        constraints = [
            # Correction #2: a plain UniqueConstraint on
            # (organization, name) does NOT stop duplicate global
            # categories, because Postgres treats NULL <> NULL for
            # uniqueness. Two partial unique indexes instead: one for
            # global rows (organization IS NULL), one for org-specific
            # rows (organization IS NOT NULL, inert in MVP but ready).
            models.UniqueConstraint(
                fields=["name"],
                condition=models.Q(organization__isnull=True),
                name="uq_category_global_name",
            ),
            models.UniqueConstraint(
                fields=["organization", "name"],
                condition=models.Q(organization__isnull=False),
                name="uq_category_org_name",
            ),
        ]

    def __str__(self):
        return self.name


DEFAULT_CATEGORIES = [
    "Staff",
    "Checkout",
    "Product Availability",
    "Product Quality",
    "Pricing",
    "Cleanliness",
    "Customer Service",
    "Store Environment",
    "Other",
]


def generate_qr_token():
    """Cryptographically random, non-sequential, URL-safe token (Phase 2 §13)."""
    return secrets.token_urlsafe(32)


class QRCode(BaseModel):
    """
    Public, revocable token identifying a branch to an anonymous scan.
    Only one active token per branch at a time; regenerating creates a
    new row and deactivates the old one, preserving history (Phase 2 §13).
    """

    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, related_name="qr_codes"
    )
    token = models.CharField(max_length=64, unique=True, default=generate_qr_token)
    is_active = models.BooleanField(default=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "qr_code"
        constraints = [
            models.UniqueConstraint(
                fields=["branch"],
                condition=models.Q(is_active=True),
                name="uq_qrcode_one_active_per_branch",
            ),
        ]

    def __str__(self):
        return f"QR({self.branch.name}, active={self.is_active})"


class Feedback(BaseModel):
    """
    A raw customer submission. Exists independently of whether it's ever
    escalated into a Complaint (Phase 2 §7).

    organization is intentionally denormalized from branch.organization
    for direct tenant-filtering — see the composite FK added in a manual
    migration (Phase 2 §D.1) which makes the DB itself reject any row
    where this drifts out of sync.
    """

    class Sentiment(models.TextChoices):
        POSITIVE = "positive", "Positive"
        NEUTRAL = "neutral", "Neutral"
        NEGATIVE = "negative", "Negative"

    class Source(models.TextChoices):
        QR = "qr", "QR Code"
        OTHER = "other", "Other"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="feedback_items"
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name="feedback_items"
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="feedback_items"
    )
    rating = models.PositiveSmallIntegerField()
    message = models.TextField(blank=True, null=True)
    sentiment = models.CharField(max_length=20, choices=Sentiment.choices)
    customer_name = models.CharField(max_length=255, blank=True, null=True)
    customer_email = models.EmailField(blank=True, null=True)
    customer_phone = models.CharField(max_length=50, blank=True, null=True)
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.QR
    )

    objects = TenantManager()

    class Meta:
        db_table = "feedback"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rating__gte=1) & models.Q(rating__lte=5),
                name="ck_feedback_rating_range",
            ),
            # Supports the composite FK from Complaint that guarantees
            # Complaint.branch always matches its parent Feedback's branch
            # (Phase 2 §D.1).
            models.UniqueConstraint(
                fields=["id", "branch"], name="uq_feedback_id_branch"
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "branch", "created_at"]),
            models.Index(fields=["category"]),
            models.Index(fields=["rating"]),
        ]

    def __str__(self):
        return f"Feedback({self.branch.name}, {self.rating}★)"

    def clean(self):
        super().clean()
        if (
            self.branch_id
            and self.organization_id
            and self.branch.organization_id != self.organization_id
        ):
            raise ValidationError(
                "Feedback branch organization does not match feedback organization."
            )
        if self.rating is not None and not (1 <= self.rating <= 5):
            raise ValidationError("Feedback rating must be between 1 and 5.")

    @staticmethod
    def derive_sentiment(rating: int) -> str:
        """MVP sentiment rule (Phase 2 §12) — no NLP, just the rating."""
        if rating <= 2:
            return Feedback.Sentiment.NEGATIVE
        if rating == 3:
            return Feedback.Sentiment.NEUTRAL
        return Feedback.Sentiment.POSITIVE

    def save(self, *args, **kwargs):
        # Enforce org/branch consistency at the application layer too,
        # not just the DB composite FK (Phase 2 §D.1 belt-and-braces).
        if self.branch_id and not self.organization_id:
            self.organization_id = self.branch.organization_id
        if not self.sentiment:
            self.sentiment = self.derive_sentiment(self.rating)
        super().save(*args, **kwargs)
