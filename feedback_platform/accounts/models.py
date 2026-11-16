from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.db.models.functions import Lower

from core.models import BaseModel
from organizations.models import Organization


class PlatformAdmin(BaseModel):
    """
    Operates the SaaS platform itself. Deliberately NOT related to
    Organization/User in any way — kept structurally separate so a bug
    can never accidentally grant org-level staff platform-wide reach
    (Phase 2 §A, §2).

    PlatformAdmin is intentionally NOT wired into Django's AUTH_USER_MODEL
    system (that slot is occupied by accounts.User, below). Its own
    authentication path uses Django's session framework directly, via a
    dedicated session key set by a dedicated login view — see
    accounts/platform_auth.py (added in a later Phase 3B checkpoint).
    This keeps the structural isolation from User intact while still
    relying on Django's own session security, not a bespoke mechanism.
    """

    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "platform_admin"

    def __str__(self):
        return self.email

    @staticmethod
    def normalize_admin_email(email):
        return email.strip().lower() if email else email

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.normalize_admin_email(self.email)
        super().save(*args, **kwargs)

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)


class UserManager(BaseUserManager):
    """
    Minimal custom manager, required because USERNAME_FIELD is "id" (see
    User docstring below) rather than Django's usual "username"/"email" —
    the default BaseUserManager.get_by_natural_key looks up by
    USERNAME_FIELD, so it must be overridden to look up by pk instead.

    create_user() is provided for convenience/consistency with Django
    conventions; it is not the primary way org Users get created in this
    app (that happens through application-level org signup/admin flows,
    a later Phase 3B/3D concern) but having it costs nothing and matches
    what `python manage.py createsuperuser`-style tooling expects to find.
    """

    def get_by_natural_key(self, pk):
        return self.get(pk=pk)

    def create_user(self, organization, email, password=None, role=None, **extra_fields):
        role = role or self.model.Role.STAFF
        user = self.model(
            organization=organization, email=self.model.normalize_user_email(email),
            role=role, **extra_fields
        )
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, organization=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", self.model.Role.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        if organization is None:
            from organizations.models import Organization
            organization, _ = Organization.objects.get_or_create(
                slug="system-admin",
                defaults={"name": "System Administration", "is_active": True},
            )

        return self.create_user(
            organization=organization, email=email, password=password, **extra_fields
        )


class User(BaseModel, AbstractBaseUser):
    """
    An organization member: Organization Admin, Manager, or Staff.
    Always belongs to exactly one organization for MVP (Phase 2 §4 —
    deliberate simplification, multi-org membership deferred).

    Email is unique per organization, not globally — see Phase 2 §B
    (User) and the org-scoped login decision (correction #3) for why.

    Email uniqueness within an organization is CASE-INSENSITIVE, enforced
    at the database level via a functional unique index on
    (LOWER(email), organization) — see uq_user_org_email_ci in Meta
    below. This was a required fix from Phase 3B Step 2 review: a plain
    (organization, email) unique constraint is case-sensitive in
    PostgreSQL, so "john@example.com" and "JOHN@example.com" could
    otherwise coexist in the same organization even though
    OrgScopedEmailBackend's lookup is case-insensitive — a real ambiguity
    the database now makes structurally impossible, not just something
    normalized away in application code. This mirrors the same
    "guarantee it in the database, not just in code" pattern used
    elsewhere in this project (Phase 2 §D.1, the UserBranch fix).

    This is Django's AUTH_USER_MODEL (see config/settings.py). It
    deliberately does NOT include PermissionsMixin — Phase 2 explicitly
    rejected Django's Group/Permission framework in favor of an explicit,
    application-level role/permission-check system, so is_superuser,
    groups, and user_permissions would be unused schema surface.

    USERNAME_FIELD is set to "id" (the UUID pk), NOT "email" — Django's
    own system checks (auth.E003) require USERNAME_FIELD to be globally
    unique, and email is deliberately org-scoped, not global. This does
    not affect real authentication: login is handled entirely by
    OrgScopedEmailBackend (a later Phase 3B checkpoint), which looks up
    (organization, email, password) directly and never consults
    USERNAME_FIELD. Verified empirically against Django's system checks
    before this was written — see the Phase 3B architecture inspection.
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Organization Admin"
        MANAGER = "manager", "Manager"
        STAFF = "staff", "Staff"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="users"
    )
    email = models.EmailField()
    full_name = models.CharField(max_length=255, blank=True, default="")
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    USERNAME_FIELD = "id"
    REQUIRED_FIELDS = ["email"]

    objects = UserManager()

    class Meta:
        db_table = "app_user"
        constraints = [
            # Case-insensitive email uniqueness within an organization —
            # required fix, Phase 3B Step 2 review. Replaces a plain
            # (organization, email) constraint, which was case-sensitive
            # in PostgreSQL and could let "john@x.com" / "JOHN@x.com"
            # coexist in the same org despite the backend's
            # case-insensitive lookup.
            models.UniqueConstraint(
                Lower("email"), "organization", name="uq_user_org_email_ci"
            ),
            # Supports the composite FK from UserBranch that guarantees a
            # user can only be linked to branches within their own
            # organization (Phase 2 follow-up fix — UserBranch tenant leak).
            # Unaffected by this AUTH_USER_MODEL change — the composite FK
            # references the app_user table/columns directly, not this
            # Python class's base classes. Confirmed in the Phase 3B
            # architecture inspection before this change was made.
            models.UniqueConstraint(
                fields=["id", "organization"], name="uq_user_id_org"
            ),
        ]

    def __str__(self):
        return f"{self.email} ({self.organization.slug}, {self.role})"

    def has_perm(self, perm, obj=None):
        return self.is_active and (self.is_superuser or self.is_staff)

    def has_perms(self, perm_list, obj=None):
        return all(self.has_perm(perm, obj) for perm in perm_list)

    def has_module_perms(self, app_label):
        return self.is_active and (self.is_superuser or self.is_staff)
    def get_all_permissions(self, obj=None):
        return set()

    def get_user_permissions(self, obj=None):
        return set()

    def get_group_permissions(self, obj=None):
        return set()

    @staticmethod
    def normalize_user_email(email):
        """Trim + lowercase. Belt-and-braces complement to the DB
        constraint above — not a substitute for it."""
        return email.strip().lower() if email else email

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.normalize_user_email(self.email)
        super().save(*args, **kwargs)
