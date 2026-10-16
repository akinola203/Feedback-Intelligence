from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from organizations.models import Branch, Organization, UserBranch


class OrganizationBranchTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="ABC Supermarkets", slug="abc")

    def test_branch_uuid_pk(self):
        branch = Branch.objects.create(organization=self.org, name="Lekki")
        self.assertEqual(len(str(branch.id)), 36)  # UUID string form

    def test_duplicate_branch_name_in_same_org_rejected(self):
        Branch.objects.create(organization=self.org, name="Lekki")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Branch.objects.create(organization=self.org, name="Lekki")

    def test_same_branch_name_allowed_in_different_orgs(self):
        other_org = Organization.objects.create(name="XYZ Stores", slug="xyz")
        Branch.objects.create(organization=self.org, name="Lekki")
        # Should NOT raise — uniqueness is scoped per organization.
        Branch.objects.create(organization=other_org, name="Lekki")


class UserOrgScopedEmailTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(name="Org A", slug="org-a")
        self.org_b = Organization.objects.create(name="Org B", slug="org-b")

    def test_duplicate_email_within_same_org_rejected(self):
        User.objects.create(
            organization=self.org_a,
            email="manager@example.com",
            password="x",
            role=User.Role.MANAGER,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create(
                    organization=self.org_a,
                    email="manager@example.com",
                    password="x",
                    role=User.Role.STAFF,
                )

    def test_same_email_allowed_across_different_orgs(self):
        # This is the scenario the org-scoped-login decision (correction
        # #3) exists to handle: one person, two organizations.
        User.objects.create(
            organization=self.org_a,
            email="consultant@example.com",
            password="x",
            role=User.Role.ADMIN,
        )
        # Should NOT raise.
        User.objects.create(
            organization=self.org_b,
            email="consultant@example.com",
            password="x",
            role=User.Role.ADMIN,
        )

    def test_password_is_hashed_not_plaintext(self):
        user = User(
            organization=self.org_a,
            email="manager2@example.com",
            role=User.Role.MANAGER,
        )
        user.set_password("correct-horse-battery-staple")
        user.save()
        self.assertNotEqual(user.password, "correct-horse-battery-staple")
        self.assertTrue(user.check_password("correct-horse-battery-staple"))
        self.assertFalse(user.check_password("wrong-password"))


class UserBranchTests(TestCase):
    def test_user_can_be_linked_to_multiple_branches(self):
        org = Organization.objects.create(name="Org C", slug="org-c")
        lekki = Branch.objects.create(organization=org, name="Lekki")
        vi = Branch.objects.create(organization=org, name="Victoria Island")
        user = User.objects.create(
            organization=org, email="john@example.com", password="x",
            role=User.Role.MANAGER,
        )
        UserBranch.objects.create(user=user, branch=lekki)
        UserBranch.objects.create(user=user, branch=vi)
        self.assertEqual(user.branch_links.count(), 2)

    def test_duplicate_user_branch_link_rejected(self):
        org = Organization.objects.create(name="Org D", slug="org-d")
        branch = Branch.objects.create(organization=org, name="Ikeja")
        user = User.objects.create(
            organization=org, email="sarah@example.com", password="x",
            role=User.Role.STAFF,
        )
        UserBranch.objects.create(user=user, branch=branch)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserBranch.objects.create(user=user, branch=branch)

    def test_organization_auto_derived_from_user(self):
        org = Organization.objects.create(name="Org J", slug="org-j")
        branch = Branch.objects.create(organization=org, name="Onikan")
        user = User.objects.create(
            organization=org, email="derive@example.com", password="x",
            role=User.Role.STAFF,
        )
        link = UserBranch.objects.create(user=user, branch=branch)
        self.assertEqual(link.organization_id, org.id)

    def test_cross_organization_userbranch_link_rejected_at_db_level(self):
        """
        This is the fix for the reported gap: a User from Organization A
        must never be linkable to a Branch belonging to Organization B.
        Bypasses the model's save() derivation on purpose (by constructing
        the instance without letting organization auto-populate correctly)
        to prove the composite FK — not just application code — is what
        actually rejects this on PostgreSQL.
        """
        from django.db import connection

        if connection.vendor != "postgresql":
            self.skipTest("Composite FK is Postgres-only; no-op on SQLite.")

        org_a = Organization.objects.create(name="Org K", slug="org-k")
        org_b = Organization.objects.create(name="Org L", slug="org-l")
        user_a = User.objects.create(
            organization=org_a, email="usera@example.com", password="x",
            role=User.Role.MANAGER,
        )
        branch_b = Branch.objects.create(organization=org_b, name="Wrong Org Branch")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                # Force organization_id to the branch's org (org_b) even
                # though the user belongs to org_a — mimics a bug that
                # skips the correct derivation logic.
                link = UserBranch(
                    user=user_a, branch=branch_b, organization=org_b
                )
                link.save()

    def test_cross_organization_link_also_rejected_via_raw_sql(self):
        """
        The strongest version of the same check: bypass the Django ORM
        entirely and attempt the cross-org link with raw SQL, confirming
        PostgreSQL's composite FKs reject it independent of any
        application-layer logic at all.
        """
        from django.db import connection

        if connection.vendor != "postgresql":
            self.skipTest("Composite FK is Postgres-only; no-op on SQLite.")

        org_a = Organization.objects.create(name="Org M", slug="org-m")
        org_b = Organization.objects.create(name="Org N", slug="org-n")
        user_a = User.objects.create(
            organization=org_a, email="rawsql@example.com", password="x",
            role=User.Role.MANAGER,
        )
        branch_b = Branch.objects.create(organization=org_b, name="Raw SQL Branch")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO user_branch
                            (id, created_at, user_id, branch_id, organization_id)
                        VALUES
                            (gen_random_uuid(), now(), %s, %s, %s)
                        """,
                        [str(user_a.id), str(branch_b.id), str(org_b.id)],
                    )

    def test_model_string_representations(self):
        org = Organization.objects.create(name="Str Org", slug="str-org")
        branch = Branch.objects.create(organization=org, name="Str Branch")
        user = User.objects.create(
            organization=org, email="str@example.com", password="x",
            role=User.Role.STAFF,
        )
        link = UserBranch.objects.create(user=user, branch=branch)
        self.assertEqual(str(org), "Str Org")
        self.assertEqual(str(branch), "Str Branch (Str Org)")
        self.assertEqual(str(link), "str@example.com @ Str Branch")

    def test_user_branch_clean_rejects_cross_org(self):
        org_a = Organization.objects.create(name="Org X", slug="org-x")
        org_b = Organization.objects.create(name="Org Y", slug="org-y")
        user_a = User.objects.create(
            organization=org_a, email="usera2@example.com", password="x",
            role=User.Role.MANAGER,
        )
        branch_b = Branch.objects.create(organization=org_b, name="Branch Y")
        link = UserBranch(user=user_a, branch=branch_b)
        with self.assertRaises(ValidationError):
            link.clean()
