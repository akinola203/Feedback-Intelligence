from django.contrib.auth import authenticate
from django.contrib.auth.context_processors import auth
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase

from accounts.backends import OrgScopedEmailBackend
from accounts.models import PlatformAdmin, User
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

    def test_user_of_inactive_organization_rejected(self):
        self.org_a.is_active = False
        self.org_a.save()
        result = self.backend.authenticate(
            None, organization=self.org_a, email="shared@example.com",
            password="password-a",
        )
        self.assertIsNone(result)

    def test_get_user_with_invalid_uuid(self):
        self.assertIsNone(self.backend.get_user("not-a-valid-uuid"))
        self.assertIsNone(self.backend.get_user(None))

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


class PlatformAdminTests(TestCase):
    def test_platform_admin_string_representation(self):
        admin = PlatformAdmin(email="admin@platform.com")
        self.assertEqual(str(admin), "admin@platform.com")

    def test_platform_admin_password_hashing(self):
        admin = PlatformAdmin(email="admin2@platform.com")
        admin.set_password("secure-password")
        admin.save()
        self.assertNotEqual(admin.password, "secure-password")
        self.assertTrue(admin.check_password("secure-password"))
        self.assertFalse(admin.check_password("wrong-password"))

    def test_platform_admin_email_normalized_on_save(self):
        admin = PlatformAdmin.objects.create(
            email="  ROOT@Platform.COM  ",
            password="x",
        )
        self.assertEqual(admin.email, "root@platform.com")

    def test_platform_admin_unique_email_enforced(self):
        PlatformAdmin.objects.create(email="unique@platform.com", password="x")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PlatformAdmin.objects.create(email="unique@platform.com", password="y")


class UserAuthCompatibilityTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org R", slug="org-r")
        self.user = User.objects.create(
            organization=self.org,
            email="user@org-r.com",
            role=User.Role.ADMIN,
        )

    def test_user_permission_methods_return_safe_defaults(self):
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertFalse(self.user.has_perm("accounts.view_user"))
        self.assertFalse(self.user.has_perms(["accounts.view_user"]))
        self.assertFalse(self.user.has_module_perms("accounts"))
        self.assertEqual(self.user.get_all_permissions(), set())
        self.assertEqual(self.user.get_user_permissions(), set())
        self.assertEqual(self.user.get_group_permissions(), set())

    def test_user_works_with_django_auth_context_processor(self):
        rf = RequestFactory()
        request = rf.get("/")
        request.user = self.user
        context = auth(request)
        self.assertIn("perms", context)
        perms_wrapper = context["perms"]
        # Evaluating permissions or app labels in template context must not raise AttributeError
        self.assertFalse(perms_wrapper["accounts"])
        self.assertFalse(perms_wrapper["accounts.view_user"])

    def test_create_user_with_default_role(self):
        user = User.objects.create_user(
            organization=self.org,
            email="defaultrole@org-r.com",
            password="secret-password",
        )
        self.assertEqual(user.role, User.Role.STAFF)
        self.assertTrue(user.check_password("secret-password"))

    def test_get_by_natural_key(self):
        retrieved = User.objects.get_by_natural_key(self.user.id)
        self.assertEqual(retrieved, self.user)

