from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.backends import OrgScopedEmailBackend
from accounts.models import User
from organizations.models import Organization


class OrgScopedEmailBackendTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(name="Org A", slug="org-a-auth")
        self.org_b = Organization.objects.create(name="Org B", slug="org-b-auth")

        self.user_a = User.objects.create(
            organization=self.org_a, email="shared@example.com", role=User.Role.MANAGER,
        )
        self.user_a.set_password("password-a")
        self.user_a.save()

        self.user_b = User.objects.create(
            organization=self.org_b, email="shared@example.com", role=User.Role.STAFF,
        )
        self.user_b.set_password("password-b")
        self.user_b.save()

        self.backend = OrgScopedEmailBackend()

    # 1. Correct org + correct email + correct password.
    def test_correct_credentials_returns_user(self):
        result = self.backend.authenticate(
            None, organization=self.org_a, email="shared@example.com", password="password-a",
        )
        self.assertEqual(result, self.user_a)

    # 2. Correct org + wrong password.
    def test_wrong_password_rejected(self):
        result = self.backend.authenticate(
            None, organization=self.org_a, email="shared@example.com", password="wrong",
        )
        self.assertIsNone(result)

    # 3. Correct org + nonexistent email.
    def test_nonexistent_email_rejected(self):
        result = self.backend.authenticate(
            None, organization=self.org_a, email="nobody@example.com", password="anything",
        )
        self.assertIsNone(result)

    # 4. Same email in both orgs — each context must return only its own user.
    def test_same_email_org_a_context_returns_org_a_user_only(self):
        result = self.backend.authenticate(
            None, organization=self.org_a, email="shared@example.com", password="password-a",
        )
        self.assertEqual(result, self.user_a)
        self.assertNotEqual(result, self.user_b)

    def test_same_email_org_b_context_returns_org_b_user_only(self):
        result = self.backend.authenticate(
            None, organization=self.org_b, email="shared@example.com", password="password-b",
        )
        self.assertEqual(result, self.user_b)
        self.assertNotEqual(result, self.user_a)

    def test_org_a_context_never_authenticates_with_org_b_password(self):
        result = self.backend.authenticate(
            None, organization=self.org_a, email="shared@example.com", password="password-b",
        )
        self.assertIsNone(result)

    def test_org_b_context_never_authenticates_with_org_a_password(self):
        result = self.backend.authenticate(
            None, organization=self.org_b, email="shared@example.com", password="password-a",
        )
        self.assertIsNone(result)

    # 5. Inactive user rejected even with correct credentials.
    def test_inactive_user_rejected(self):
        inactive = User.objects.create(
            organization=self.org_a, email="inactive@example.com",
            role=User.Role.STAFF, is_active=False,
        )
        inactive.set_password("correct-password")
        inactive.save()

        result = self.backend.authenticate(
            None, organization=self.org_a, email="inactive@example.com",
            password="correct-password",
        )
        self.assertIsNone(result)

    # 6. Missing/invalid organization context rejected safely.
    def test_missing_organization_rejected(self):
        result = self.backend.authenticate(
            None, organization=None, email="shared@example.com", password="password-a",
        )
        self.assertIsNone(result)

    def test_invalid_organization_type_rejected(self):
        # A raw id/string instead of a resolved Organization instance must
        # never be silently coerced into a lookup — the backend does not
        # resolve organizations itself.
        result = self.backend.authenticate(
            None, organization=str(self.org_a.id), email="shared@example.com",
            password="password-a",
        )
        self.assertIsNone(result)

    def test_missing_email_or_password_rejected(self):
        self.assertIsNone(
            self.backend.authenticate(None, organization=self.org_a, email=None, password="x")
        )
        self.assertIsNone(
            self.backend.authenticate(
                None, organization=self.org_a, email="shared@example.com", password=None
            )
        )

    # 7. Must not disclose whether the email exists in another organization —
    # every rejection path returns the identical None value.
    def test_response_identical_for_nonexistent_and_wrong_org_email(self):
        result_nonexistent = self.backend.authenticate(
            None, organization=self.org_a, email="totally-unknown@example.com",
            password="whatever",
        )
        org_c = Organization.objects.create(name="Org C", slug="org-c-auth")
        result_wrong_org = self.backend.authenticate(
            None, organization=org_c, email="shared@example.com", password="whatever",
        )
        self.assertIsNone(result_nonexistent)
        self.assertIsNone(result_wrong_org)
        self.assertEqual(type(result_nonexistent), type(result_wrong_org))

    # 8. Must work through Django's standard authenticate() API, not just
    # by calling the backend method directly.
    def test_works_through_django_authenticate(self):
        result = authenticate(
            request=None, organization=self.org_a, email="shared@example.com",
            password="password-a",
        )
        self.assertEqual(result, self.user_a)

    def test_django_authenticate_rejects_cross_org_password(self):
        result = authenticate(
            request=None, organization=self.org_a, email="shared@example.com",
            password="password-b",
        )
        self.assertIsNone(result)

    def test_django_authenticate_with_unrelated_credential_shape(self):
        # Simulates something calling Django's authenticate() with a
        # completely different credential shape (e.g. a hypothetical
        # future admin login) — must not raise, must reject.
        result = authenticate(request=None, username="whoever", password="whatever")
        self.assertIsNone(result)


class CaseInsensitiveEmailUniquenessTests(TestCase):
    """
    Phase 3B Step 2 review fix: uq_user_org_email_ci must make
    case-variant duplicate emails structurally impossible within an
    organization, at the database level — not just discouraged by
    application-layer normalization.
    """

    def setUp(self):
        self.org_a = Organization.objects.create(name="Org P", slug="org-p-ci")
        self.org_b = Organization.objects.create(name="Org Q", slug="org-q-ci")

    # 1. Case-variant emails cannot coexist in the same organization.
    def test_case_variant_emails_rejected_in_same_org(self):
        User.objects.create(
            organization=self.org_a, email="john@example.com", role=User.Role.STAFF,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create(
                    organization=self.org_a, email="JOHN@example.com",
                    role=User.Role.MANAGER,
                )

    def test_mixed_case_variants_also_rejected(self):
        User.objects.create(
            organization=self.org_a, email="Jane@Example.com", role=User.Role.STAFF,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create(
                    organization=self.org_a, email="jane@example.COM",
                    role=User.Role.MANAGER,
                )

    # 2. The same normalized email can still exist in different orgs.
    def test_same_normalized_email_allowed_across_different_orgs(self):
        User.objects.create(
            organization=self.org_a, email="shared2@example.com", role=User.Role.ADMIN,
        )
        # Should NOT raise — a case-variant of the same email in a
        # DIFFERENT organization is a completely separate identity.
        User.objects.create(
            organization=self.org_b, email="SHARED2@example.com", role=User.Role.ADMIN,
        )

    # 3. Authentication remains case-insensitive and deterministic.
    def test_authentication_is_case_insensitive_and_deterministic(self):
        user = User.objects.create(
            organization=self.org_a, email="deterministic@example.com",
            role=User.Role.MANAGER,
        )
        user.set_password("correct-password")
        user.save()

        backend = OrgScopedEmailBackend()

        # Login with a differently-cased version of the stored email
        # still resolves to the single, correct user.
        result = backend.authenticate(
            None, organization=self.org_a, email="DETERMINISTIC@EXAMPLE.COM",
            password="correct-password",
        )
        self.assertEqual(result, user)

    def test_authentication_deterministic_with_cross_org_case_variants(self):
        user_a = User.objects.create(
            organization=self.org_a, email="crosscase@example.com", role=User.Role.MANAGER,
        )
        user_a.set_password("password-a")
        user_a.save()

        user_b = User.objects.create(
            organization=self.org_b, email="CROSSCASE@example.com", role=User.Role.STAFF,
        )
        user_b.set_password("password-b")
        user_b.save()

        backend = OrgScopedEmailBackend()

        result_a = backend.authenticate(
            None, organization=self.org_a, email="crosscase@example.com",
            password="password-a",
        )
        result_b = backend.authenticate(
            None, organization=self.org_b, email="crosscase@example.com",
            password="password-b",
        )
        self.assertEqual(result_a, user_a)
        self.assertEqual(result_b, user_b)
        self.assertNotEqual(result_a, result_b)
