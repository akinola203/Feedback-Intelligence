from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

from organizations.models import Organization

User = get_user_model()


class OrgScopedEmailBackend(BaseBackend):
    """
    Authenticates organization Users against (organization, email,
    password), per the Phase 2 org-scoped-login decision (correction #3)
    and the approved Phase 3B architecture.

    IMPORTANT: `organization` must be an already-resolved Organization
    instance. This backend deliberately does NOT accept a raw
    organization id/slug string and look it up itself — resolving the
    slug from the URL into a real Organization is the login view's job
    (a later Phase 3B checkpoint, not yet implemented). Keeping that
    resolution out of this backend means a client can never smuggle an
    arbitrary organization identifier into the credentials dict and have
    this backend trust it; it only ever authenticates against an
    Organization object the caller has already validated exists.

    Deliberately does NOT authenticate PlatformAdmin — that stays on its
    own session-based path entirely outside django.contrib.auth, per the
    Phase 2 §2/§A structural separation. This backend only ever queries
    accounts.User.

    Registered as the platform's only entry in AUTHENTICATION_BACKENDS
    (see config/settings.py) — Django's default ModelBackend is not used
    for accounts.User, since ModelBackend's globally-unique-username
    lookup model doesn't fit an identity that's deliberately scoped per
    organization.
    """

    def authenticate(self, request, organization=None, email=None, password=None, **kwargs):
        if not isinstance(organization, Organization) or not email or password is None:
            # Missing or invalid organization context, or missing
            # credentials: reject without touching the database, so an
            # invalid organization can never be used to probe for valid
            # emails via timing or error differences.
            return None

        # Normalize the same way User.save() does: trim + lowercase. The
        # database now enforces case-insensitive uniqueness within an
        # organization (uq_user_org_email_ci), so this lookup can safely
        # use .get() — no .first() needed, and no possibility of an
        # arbitrary pick among case-variant duplicates, because the
        # database structurally prevents those duplicates from existing.
        normalized_email = email.strip().lower()

        try:
            user = User.objects.get(organization=organization, email__iexact=normalized_email)
        except User.DoesNotExist:
            # Run the password hasher against a throwaway instance
            # anyway, mirroring Django's own ModelBackend. This costs
            # roughly the same time as a real check_password() call, so
            # a nonexistent email in this organization doesn't respond
            # measurably faster than a real one — a timing-attack
            # mitigation against user enumeration, on top of returning
            # the identical None value for every rejection path here.
            User().set_password(password)
            return None

        if not user.check_password(password):
            return None

        if not self.user_can_authenticate(user):
            return None

        return user

    def user_can_authenticate(self, user):
        """Reject inactive users — mirrors Django's ModelBackend."""
        return getattr(user, "is_active", False)

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            return None
