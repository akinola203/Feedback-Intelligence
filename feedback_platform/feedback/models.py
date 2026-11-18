import asyncio
import inspect
import logging
import secrets

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from core.managers import TenantManager
from core.models import BaseModel
from organizations.models import Branch, Organization

logger = logging.getLogger(__name__)

WS_BROADCAST_TIMEOUT_SECONDS = 2.0


def _dispatch_negative_feedback_alert(group_name: str, payload: dict) -> None:
    """
    Dispatches a negative feedback alert to the Channels group with strict
    timeout and backpressure exception boundaries so Redis hiccups or
    ChannelFull conditions never crash or block HTTP feedback submissions.
    """
    try:
        from asgiref.sync import async_to_sync
        from channels.exceptions import ChannelFull
        from channels.layers import get_channel_layer
    except Exception as exc:
        logger.warning("Channels unavailable for WebSocket broadcast: %s", exc)
        return

    try:
        from redis.exceptions import RedisError
    except ImportError:
        RedisError = ()  # type: ignore[assignment]

    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    async def _send_with_timeout():
        result = channel_layer.group_send(group_name, payload)
        if inspect.isawaitable(result):
            await asyncio.wait_for(result, timeout=WS_BROADCAST_TIMEOUT_SECONDS)

    try:
        async_to_sync(_send_with_timeout)()
    except ChannelFull as exc:
        logger.warning(
            "WebSocket backpressure (ChannelFull) dropping alert for group %s: %s",
            group_name,
            exc,
        )
    except (TimeoutError, asyncio.TimeoutError) as exc:
        logger.warning(
            "WebSocket broadcast timed out after %.1fs for group %s: %s",
            WS_BROADCAST_TIMEOUT_SECONDS,
            group_name,
            exc,
        )
    except (ConnectionError, OSError) as exc:
        logger.warning(
            "WebSocket broker connection error for group %s: %s",
            group_name,
            exc,
        )
    except Exception as exc:
        if RedisError and isinstance(exc, RedisError):
            logger.warning(
                "RedisError during WebSocket broadcast for group %s: %s",
                group_name,
                exc,
            )
        else:
            logger.warning(
                "Unexpected error during WebSocket broadcast for group %s: %s",
                group_name,
                exc,
            )


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

    @classmethod
    def rotate_for_branch(cls, branch):
        """
        Atomically locks the parent Branch row via SELECT ... FOR UPDATE,
        revokes any existing active QR codes for the branch, and issues a
        fresh active token without violating uq_qrcode_one_active_per_branch.
        """
        with transaction.atomic():
            locked_branch = Branch.objects.select_for_update().get(pk=branch.pk)
            cls.objects.filter(branch=locked_branch, is_active=True).update(
                is_active=False, revoked_at=timezone.now()
            )
            return cls.objects.create(branch=locked_branch, is_active=True)


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
        if self.category_id and self.organization_id:
            if (
                self.category.organization_id is not None
                and self.category.organization_id != self.organization_id
            ):
                raise ValidationError(
                    "Selected category does not belong to this organization or global defaults."
                )
        if self.rating is not None and not (1 <= self.rating <= 5):
            raise ValidationError("Feedback rating must be between 1 and 5.")

    @staticmethod
    def derive_sentiment(rating: int) -> str:
        """MVP sentiment rule (Phase 2 §12) — no NLP, just the rating."""
        if rating is None:
            return Feedback.Sentiment.NEUTRAL
        if rating <= 2:
            return Feedback.Sentiment.NEGATIVE
        if rating == 3:
            return Feedback.Sentiment.NEUTRAL
        return Feedback.Sentiment.POSITIVE

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        # Enforce org/branch consistency at the application layer too,
        # not just the DB composite FK (Phase 2 §D.1 belt-and-braces).
        if self.branch_id and not self.organization_id:
            self.organization_id = self.branch.organization_id
        if self.rating is not None:
            self.sentiment = self.derive_sentiment(self.rating)
        elif not self.sentiment:
            self.sentiment = Feedback.Sentiment.NEUTRAL
        super().save(*args, **kwargs)

        if is_new and self.organization_id:
            org_id = self.organization_id
            branch_id = self.branch_id

            # Version-bump analytics cache only after DB commit succeeds
            from .cache import bump_analytics_cache_version
            transaction.on_commit(
                lambda oid=org_id, bid=branch_id: bump_analytics_cache_version(oid, bid)
            )

            if self.rating is not None and self.rating <= 2:
                # Extract plain scalars before commit so on_commit does zero ORM/DB I/O
                branch_name = self.branch.name if self.branch_id else "Unknown Branch"
                category_name = self.category.name if self.category_id else "General"
                group_name = f"org_{org_id}_alerts"
                alert_payload = {
                    "type": "negative_feedback_alert",
                    "content": {
                        "event": "negative_feedback_alert",
                        "id": str(self.id),
                        "branch_id": str(branch_id),
                        "branch_name": branch_name,
                        "category": category_name,
                        "rating": self.rating,
                        "sentiment": self.sentiment,
                        "message": self.message or "",
                        "customer_name": self.customer_name or "Anonymous",
                        "created_at": (
                            self.created_at.isoformat()
                            if getattr(self, "created_at", None)
                            else None
                        ),
                    },
                }
                transaction.on_commit(
                    lambda grp=group_name, data=alert_payload: _dispatch_negative_feedback_alert(
                        grp, data
                    )
                )
