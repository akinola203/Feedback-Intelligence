from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.backends import OrgScopedEmailBackend
from accounts.models import User
from audit.models import AuditLog
from complaints.models import Complaint
from organizations.models import Branch, Organization, UserBranch
from .models import Category, Feedback, QRCode


class SecurityAndEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # Tenant A Setup
        self.org_a = Organization.objects.create(name="Supermarket A", slug="org-a", is_active=True)
        self.branch_a1 = Branch.objects.create(organization=self.org_a, name="Lekki A1", is_active=True)
        self.branch_a2 = Branch.objects.create(organization=self.org_a, name="Ikeja A2", is_active=True)

        self.admin_a = User.objects.create_user(
            organization=self.org_a, email="admin@org-a.com", password="Password123!", role=User.Role.ADMIN
        )
        self.manager_a1 = User.objects.create_user(
            organization=self.org_a, email="manager1@org-a.com", password="Password123!", role=User.Role.MANAGER
        )
        UserBranch.objects.create(user=self.manager_a1, branch=self.branch_a1)

        # Tenant B Setup
        self.org_b = Organization.objects.create(name="Supermarket B", slug="org-b", is_active=True)
        self.branch_b1 = Branch.objects.create(organization=self.org_b, name="Victoria Island B1", is_active=True)

        self.manager_b = User.objects.create_user(
            organization=self.org_b, email="manager@org-b.com", password="Password123!", role=User.Role.MANAGER
        )
        UserBranch.objects.create(user=self.manager_b, branch=self.branch_b1)

        # Categories
        self.cat_global = Category.objects.create(name="Staff Service", organization=None)
        self.cat_org_a = Category.objects.create(name="VIP Valet", organization=self.org_a)
        self.cat_org_b = Category.objects.create(name="Bakery Special", organization=self.org_b)

        # QR Codes
        self.qr_a1 = QRCode.objects.create(branch=self.branch_a1, is_active=True)

    def tearDown(self):
        cache.clear()

    # 1. Zombie Session Tests
    def test_zombie_session_rejected_when_user_deactivated(self):
        backend = OrgScopedEmailBackend()
        self.assertEqual(backend.get_user(self.manager_a1.id), self.manager_a1)

        self.manager_a1.is_active = False
        self.manager_a1.save()

        self.assertIsNone(backend.get_user(self.manager_a1.id))

    def test_zombie_session_rejected_when_organization_suspended(self):
        backend = OrgScopedEmailBackend()
        self.assertEqual(backend.get_user(self.manager_a1.id), self.manager_a1)

        self.org_a.is_active = False
        self.org_a.save()

        self.assertIsNone(backend.get_user(self.manager_a1.id))

    # 2. Cross-Tenant Category Rejection
    def test_cross_tenant_category_rejected_with_400(self):
        url = reverse("public-feedback-submit", kwargs={"token": self.qr_a1.token})
        payload = {
            "rating": 4,
            "category": str(self.cat_org_b.id),  # Org B category for Org A branch!
            "message": "Attempting cross-tenant category breach.",
        }
        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Category is invalid for this store branch", res.data.get("error", ""))

    def test_global_and_own_category_accepted(self):
        url = reverse("public-feedback-submit", kwargs={"token": self.qr_a1.token})

        res1 = self.client.post(
            url,
            {"rating": 5, "category": str(self.cat_global.id), "message": "Global OK"},
            format="json",
        )
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        res2 = self.client.post(
            url,
            {"rating": 4, "category": str(self.cat_org_a.id), "message": "Org A OK"},
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)

    # 3. Public Rate Limiting Test
    def test_public_rate_limiting_triggers_429(self):
        url = reverse("public-feedback-submit", kwargs={"token": self.qr_a1.token})
        payload = {"rating": 5, "category": str(self.cat_global.id), "message": "Rate check"}

        client = APIClient(REMOTE_ADDR="197.210.64.1")

        for i in range(10):
            res = client.post(url, payload, format="json")
            self.assertEqual(res.status_code, status.HTTP_201_CREATED, f"Failed at request {i+1}")

        res_throttled = client.post(url, payload, format="json")
        self.assertEqual(res_throttled.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    # 4. Secure QR Download RBAC Tests
    def test_download_qr_code_requires_authentication(self):
        url = reverse("download-qr-code", kwargs={"branch_id": self.branch_a1.id})
        res = self.client.get(url)
        self.assertIn(res.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_download_qr_code_forbidden_for_other_tenant_or_unassigned_manager(self):
        url = reverse("download-qr-code", kwargs={"branch_id": self.branch_a1.id})
        self.client.force_authenticate(user=self.manager_b)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # Manager from same org but unassigned branch
        url_unassigned = reverse("download-qr-code", kwargs={"branch_id": self.branch_a2.id})
        self.client.force_authenticate(user=self.manager_a1)
        res_unassigned = self.client.get(url_unassigned)
        self.assertEqual(res_unassigned.status_code, status.HTTP_403_FORBIDDEN)

    def test_download_qr_code_succeeds_with_valid_png_stream(self):
        url = reverse("download-qr-code", kwargs={"branch_id": self.branch_a1.id})
        self.client.force_authenticate(user=self.manager_a1)

        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res["Content-Type"], "image/png")
        self.assertTrue(res.content.startswith(b"\x89PNG\r\n\x1a\n"))

    # 5. Manager Analytics Aggregation & Scoping
    def test_manager_analytics_aggregates_and_scopes_by_branch(self):
        Feedback.objects.create(
            organization=self.org_a, branch=self.branch_a1, category=self.cat_global, rating=5
        )
        Feedback.objects.create(
            organization=self.org_a, branch=self.branch_a1, category=self.cat_global, rating=1
        )
        Feedback.objects.create(
            organization=self.org_a, branch=self.branch_a2, category=self.cat_global, rating=4
        )

        url = reverse("manager-analytics-overview")
        self.client.force_authenticate(user=self.manager_a1)

        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Manager A1 is only linked to branch_a1, so count must be 2, not 3
        self.assertEqual(res.data["summary"]["total_feedback"], 2)
        self.assertEqual(res.data["summary"]["average_rating"], 3.0)
        self.assertEqual(res.data["sentiment"]["positive"]["count"], 1)
        self.assertEqual(res.data["sentiment"]["negative"]["count"], 1)

        # Trying to query branch_a2 explicitly must return 403 Forbidden
        res_forbidden = self.client.get(f"{url}?branch_id={self.branch_a2.id}")
        self.assertEqual(res_forbidden.status_code, status.HTTP_403_FORBIDDEN)

    # 6. Model Enhancements & Edge Cases
    def test_qrcode_rotate_for_branch(self):
        old_token = self.qr_a1.token
        new_qr = QRCode.rotate_for_branch(self.branch_a1)

        self.qr_a1.refresh_from_db()
        self.assertFalse(self.qr_a1.is_active)
        self.assertIsNotNone(self.qr_a1.revoked_at)

        self.assertTrue(new_qr.is_active)
        self.assertNotEqual(new_qr.token, old_token)

    def test_audit_log_delete_prevented(self):
        log = AuditLog.objects.create(
            organization=self.org_a,
            actor_user=self.admin_a,
            entity_type="TestEntity",
            entity_id=self.branch_a1.id,
            action="TEST_ACTION",
        )
        with self.assertRaises(PermissionDenied):
            log.delete()

    def test_complaint_assigned_to_branch_validation(self):
        feedback = Feedback.objects.create(
            organization=self.org_a, branch=self.branch_a1, category=self.cat_global, rating=2
        )
        # manager_a1 is linked to branch_a1 -> OK
        complaint = Complaint(
            feedback=feedback,
            branch=self.branch_a1,
            organization=self.org_a,
            created_by=self.admin_a,
            assigned_to=self.manager_a1,
        )
        complaint.full_clean()

        # Manager from different branch
        manager_a2 = User.objects.create_user(
            organization=self.org_a, email="manager2@org-a.com", password="Password123!", role=User.Role.MANAGER
        )
        UserBranch.objects.create(user=manager_a2, branch=self.branch_a2)

        complaint_invalid = Complaint(
            feedback=feedback,
            branch=self.branch_a1,
            organization=self.org_a,
            created_by=self.admin_a,
            assigned_to=manager_a2,
        )
        with self.assertRaises(ValidationError):
            complaint_invalid.full_clean()
