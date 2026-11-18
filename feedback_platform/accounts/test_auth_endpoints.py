from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from organizations.models import Branch, Organization, UserBranch


class AuthEndpointsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # Tenant Org
        self.org = Organization.objects.create(
            name="MegaMart Stores", slug="megamart", is_active=True
        )
        self.branch1 = Branch.objects.create(
            organization=self.org, name="Victoria Island Branch", is_active=True
        )
        self.branch2 = Branch.objects.create(
            organization=self.org, name="Yaba Branch", is_active=True
        )

        # Users
        self.admin_user = User.objects.create_user(
            organization=self.org,
            email="admin@megamart.com",
            password="AdminPassword123!",
            role=User.Role.ADMIN,
            full_name="MegaMart Admin",
            is_staff=True,
        )

        self.manager_user = User.objects.create_user(
            organization=self.org,
            email="manager@megamart.com",
            password="ManagerPassword123!",
            role=User.Role.MANAGER,
            full_name="VI Manager",
        )
        UserBranch.objects.create(user=self.manager_user, branch=self.branch1)

        self.inactive_user = User.objects.create_user(
            organization=self.org,
            email="inactive@megamart.com",
            password="Password123!",
            role=User.Role.STAFF,
            is_active=False,
        )

        self.login_url = reverse("auth-login")
        self.logout_url = reverse("auth-logout")
        self.me_url = reverse("auth-me")

    def test_login_successful_and_sets_session_cookie(self):
        payload = {
            "organization_slug": "megamart",
            "email": "manager@megamart.com",
            "password": "ManagerPassword123!",
        }
        response = self.client.post(self.login_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "manager@megamart.com")
        self.assertEqual(response.data["role"], "manager")
        self.assertEqual(response.data["organization_slug"], "megamart")
        self.assertEqual(len(response.data["branches"]), 1)
        self.assertEqual(response.data["branches"][0]["id"], str(self.branch1.id))

        # Check session cookie exists
        self.assertIn("sessionid", response.cookies)

    def test_admin_login_returns_all_organization_branches(self):
        payload = {
            "organization_slug": "megamart",
            "email": "admin@megamart.com",
            "password": "AdminPassword123!",
        }
        response = self.client.post(self.login_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["branches"]), 2)

    def test_login_without_org_slug_resolves_unique_email_and_rejects_ambiguous(self):
        # Unique email resolves cleanly without organization_slug
        resp_unique = self.client.post(
            self.login_url,
            {"email": "manager@megamart.com", "password": "ManagerPassword123!"},
            format="json",
        )
        self.assertEqual(resp_unique.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_unique.data["organization_slug"], "megamart")

        # Create second org with identical email -> omitting slug must fail uniformly with 401
        org2 = Organization.objects.create(name="OtherMart", slug="othermart", is_active=True)
        User.objects.create_user(
            organization=org2,
            email="manager@megamart.com",
            password="OtherPassword123!",
            role=User.Role.MANAGER,
        )
        cache.clear()
        resp_ambiguous = self.client.post(
            self.login_url,
            {"email": "manager@megamart.com", "password": "ManagerPassword123!"},
            format="json",
        )
        self.assertEqual(resp_ambiguous.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(resp_ambiguous.data, {"error": "Invalid credentials."})

    def test_login_fails_with_invalid_organization_slug(self):
        payload = {
            "organization_slug": "nonexistent-slug",
            "email": "manager@megamart.com",
            "password": "ManagerPassword123!",
        }
        response = self.client.post(self.login_url, payload, format="json")
        # Uniform 401 prevents organization/user enumeration
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"], "Invalid credentials.")

    def test_login_fails_with_wrong_password(self):
        payload = {
            "organization_slug": "megamart",
            "email": "manager@megamart.com",
            "password": "WrongPassword!",
        }
        response = self.client.post(self.login_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"], "Invalid credentials.")

    def test_login_fails_for_deactivated_user(self):
        payload = {
            "organization_slug": "megamart",
            "email": "inactive@megamart.com",
            "password": "Password123!",
        }
        response = self.client.post(self.login_url, payload, format="json")
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_current_user_me_unauthenticated_returns_401(self):
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_current_user_me_authenticated_returns_profile(self):
        self.client.force_authenticate(user=self.manager_user)
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "manager@megamart.com")
        self.assertEqual(response.data["full_name"], "VI Manager")

    def test_logout_clears_session(self):
        self.client.force_authenticate(user=self.manager_user)
        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Successfully logged out.")

    def test_create_superuser_and_admin_authentication(self):
        su = User.objects.create_superuser(
            email="platform.super@megamart.com",
            password="SuperPassword123!",
        )
        self.assertTrue(su.is_staff)
        self.assertTrue(su.is_superuser)
        self.assertTrue(su.has_perm("any_perm"))
        self.assertTrue(su.has_module_perms("any_app"))

        # Verify backend allows staff authentication without organization context
        from django.contrib.auth import authenticate
        auth_user = authenticate(
            username="platform.super@megamart.com",
            password="SuperPassword123!",
        )
        self.assertEqual(auth_user, su)


class DemoDataCommandTests(TestCase):
    def test_seed_demo_data_command_runs_cleanly(self):
        call_command("seed_demo_data")
        # Verify freshmart organization exists
        org = Organization.objects.filter(slug="freshmart").first()
        self.assertIsNotNone(org)
        self.assertEqual(org.branches.count(), 2)
        self.assertEqual(org.users.count(), 3)
        self.assertEqual(org.feedback_items.count(), 25)
        self.assertEqual(org.complaints.count(), 5)
