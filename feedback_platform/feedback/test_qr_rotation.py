from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from feedback.models import QRCode
from organizations.models import Branch, Organization, UserBranch


class RotateQRCodeEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Org A
        self.org_a = Organization.objects.create(name="Supermarket A", slug="org-a", is_active=True)
        self.branch_a1 = Branch.objects.create(organization=self.org_a, name="Branch A1", is_active=True)
        self.branch_a2 = Branch.objects.create(organization=self.org_a, name="Branch A2", is_active=True)

        self.admin_a = User.objects.create_user(
            organization=self.org_a,
            email="admin@org-a.com",
            password="Password123!",
            role=User.Role.ADMIN,
        )
        self.manager_a1 = User.objects.create_user(
            organization=self.org_a,
            email="manager1@org-a.com",
            password="Password123!",
            role=User.Role.MANAGER,
        )
        UserBranch.objects.create(user=self.manager_a1, branch=self.branch_a1)

        # Org B
        self.org_b = Organization.objects.create(name="Supermarket B", slug="org-b", is_active=True)
        self.branch_b = Branch.objects.create(organization=self.org_b, name="Branch B", is_active=True)
        self.manager_b = User.objects.create_user(
            organization=self.org_b,
            email="manager@org-b.com",
            password="Password123!",
            role=User.Role.MANAGER,
        )
        UserBranch.objects.create(user=self.manager_b, branch=self.branch_b)

        # Initial QR code for branch A1
        self.qr_a1 = QRCode.objects.create(branch=self.branch_a1, is_active=True)

    def test_rotate_qr_code_requires_authentication(self):
        url = reverse("rotate-qr-code", kwargs={"branch_id": self.branch_a1.id})
        response = self.client.post(url)
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_assigned_manager_can_rotate_qr_code(self):
        self.client.force_authenticate(user=self.manager_a1)
        url = reverse("rotate-qr-code", kwargs={"branch_id": self.branch_a1.id})
        old_token = self.qr_a1.token

        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.data)
        self.assertNotEqual(response.data["token"], old_token)
        self.assertEqual(response.data["branch_id"], str(self.branch_a1.id))

        # Verify old QR code is deactivated
        self.qr_a1.refresh_from_db()
        self.assertFalse(self.qr_a1.is_active)
        self.assertIsNotNone(self.qr_a1.revoked_at)

        # Verify new active QR in DB
        active_qr = QRCode.objects.get(branch=self.branch_a1, is_active=True)
        self.assertEqual(active_qr.token, response.data["token"])

    def test_manager_cannot_rotate_unassigned_branch_in_same_org(self):
        self.client.force_authenticate(user=self.manager_a1)
        # Attempt to rotate branch A2 which manager_a1 is not linked to
        url = reverse("rotate-qr-code", kwargs={"branch_id": self.branch_a2.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("do not have permission", str(response.data))

    def test_manager_cannot_rotate_branch_in_different_org(self):
        self.client.force_authenticate(user=self.manager_a1)
        # Attempt to rotate branch B from Org B
        url = reverse("rotate-qr-code", kwargs={"branch_id": self.branch_b.id})
        response = self.client.post(url)
        # 404 because branch_b is not found in user's organization
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_rotate_any_branch_in_their_org(self):
        self.client.force_authenticate(user=self.admin_a)
        url = reverse("rotate-qr-code", kwargs={"branch_id": self.branch_a2.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["branch_id"], str(self.branch_a2.id))
