import asyncio
from unittest.mock import patch

from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from accounts.serializers import UserProfileSerializer
from complaints.models import Complaint
from feedback.consumers import ManagerAlertConsumer
from feedback.models import Category, Feedback, QRCode
from organizations.models import Branch, Organization, UserBranch


class AppSecAuditTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        self.org_a = Organization.objects.create(name="SuperMart <A> & Co", slug="supermart-a", is_active=True)
        self.branch_lekki = Branch.objects.create(organization=self.org_a, name="Lekki <Phase 1> & Mall", is_active=True)
        self.branch_ikeja = Branch.objects.create(organization=self.org_a, name="Ikeja City Mall", is_active=True)

        self.admin_a = User.objects.create_user(
            organization=self.org_a,
            email="admin@supermart-a.ng",
            password="StrongPassword123!",
            role=User.Role.ADMIN,
        )
        self.manager_lekki = User.objects.create_user(
            organization=self.org_a,
            email="lekki@supermart-a.ng",
            password="StrongPassword123!",
            role=User.Role.MANAGER,
        )
        UserBranch.objects.create(user=self.manager_lekki, branch=self.branch_lekki)

        self.org_b = Organization.objects.create(name="RivalMart", slug="rivalmart-b", is_active=True)
        self.branch_b = Branch.objects.create(organization=self.org_b, name="Abuja Central", is_active=True)
        self.manager_b = User.objects.create_user(
            organization=self.org_b,
            email="mgr@rivalmart-b.ng",
            password="StrongPassword123!",
            role=User.Role.MANAGER,
        )
        UserBranch.objects.create(user=self.manager_b, branch=self.branch_b)

        self.category = Category.objects.create(name="Freshness & Quality", organization=None, is_active=True)
        self.qr_lekki = QRCode.objects.create(branch=self.branch_lekki, is_active=True)

    def tearDown(self):
        cache.clear()

    # Check #5: Idempotency & Race Conditions on Feedback Submission
    def test_feedback_double_tap_deduplicates_without_duplicate_rows_or_alerts(self):
        channel_layer = get_channel_layer()
        url = reverse("public-feedback-submit", kwargs={"token": self.qr_lekki.token})
        payload = {
            "rating": 1,
            "category": str(self.category.id),
            "message": "Network lagged so I tapped twice!",
            "customer_name": "Tunde",
        }

        with patch.object(channel_layer, "group_send") as mock_send:
            with self.captureOnCommitCallbacks(execute=True):
                resp1 = self.client.post(url, payload, format="json")
                resp2 = self.client.post(url, payload, format="json")

        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp1.data["id"], resp2.data["id"])
        self.assertEqual(resp2.get("X-Idempotent-Replay"), "true")
        # Strictly 1 DB row created and 1 broadcast batch (org + branch = 2 group_send calls)
        self.assertEqual(Feedback.objects.filter(branch=self.branch_lekki).count(), 1)
        self.assertEqual(mock_send.call_count, 2)

    def test_different_message_from_same_ip_is_not_deduplicated(self):
        url = reverse("public-feedback-submit", kwargs={"token": self.qr_lekki.token})
        resp1 = self.client.post(
            url,
            {"rating": 5, "category": str(self.category.id), "message": "First review"},
            format="json",
        )
        resp2 = self.client.post(
            url,
            {"rating": 5, "category": str(self.category.id), "message": "Second review"},
            format="json",
        )
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(resp1.data["id"], resp2.data["id"])
        self.assertEqual(Feedback.objects.filter(branch=self.branch_lekki).count(), 2)

    # Check #6: ReportLab PDF XML/SSRF Injection Defense & Concurrency Backpressure
    def test_pdf_export_escapes_malicious_xml_and_ssrf_tags(self):
        Feedback.objects.create(
            organization=self.org_a,
            branch=self.branch_lekki,
            category=self.category,
            rating=1,
            customer_name='<img src="http://169.254.169.254/latest/meta-data/"/> <b>Attacker',
            message='<font color="red"><para>Unclosed tag & <script>alert(1)</script>',
        )

        self.client.force_authenticate(user=self.admin_a)
        url = reverse("executive-pdf-report")
        response = self.client.get(f"{url}?days=99999999")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_pdf_export_rejects_concurrent_export_per_user(self):
        self.client.force_authenticate(user=self.admin_a)
        url = reverse("executive-pdf-report")
        cache.set(f"pdf_export_lock:{self.admin_a.id}", "1", timeout=15)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    # Check #8 & #11: Cross-Tenant Complaint Assignment IDOR & Mass Assignment Locking
    def test_complaint_patch_blocks_cross_tenant_assigned_to_and_forged_resolved_at(self):
        fb = Feedback.objects.create(
            organization=self.org_a,
            branch=self.branch_lekki,
            category=self.category,
            rating=1,
            message="Dirty floor.",
        )
        complaint = Complaint.objects.create(
            feedback=fb,
            organization=self.org_a,
            branch=self.branch_lekki,
            status=Complaint.Status.NEW,
            priority=Complaint.Priority.HIGH,
            created_by=self.admin_a,
        )

        self.client.force_authenticate(user=self.admin_a)
        url = reverse("complaint-detail", kwargs={"id": complaint.id})

        # Attempt cross-tenant user assignment
        resp_idor = self.client.patch(url, {"assigned_to": str(self.manager_b.id)}, format="json")
        self.assertEqual(resp_idor.status_code, status.HTTP_400_BAD_REQUEST)

        # Attempt forging resolved_at while keeping status=new
        resp_forge = self.client.patch(
            url,
            {"status": Complaint.Status.NEW, "resolved_at": "2020-01-01T00:00:00Z"},
            format="json",
        )
        self.assertEqual(resp_forge.status_code, status.HTTP_200_OK)
        complaint.refresh_from_db()
        self.assertIsNone(complaint.resolved_at)

    def test_user_profile_serializer_locks_privilege_fields_read_only(self):
        read_only = set(UserProfileSerializer.Meta.read_only_fields)
        for sensitive in ("is_staff", "is_superuser", "role", "organization_id", "email"):
            self.assertIn(sensitive, read_only)

    # Check #10: Login Rate Limiting & Anti-Enumeration
    def test_login_returns_uniform_401_and_throttles_credential_stuffing(self):
        url = reverse("auth-login")
        cases = [
            {"organization_slug": "no-such-org", "email": "x@y.com", "password": "wrong"},
            {"organization_slug": "supermart-a", "email": "nobody@supermart-a.ng", "password": "wrong"},
            {"organization_slug": "supermart-a", "email": "admin@supermart-a.ng", "password": "wrong"},
        ]
        for payload in cases:
            resp = self.client.post(url, payload, format="json")
            self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
            self.assertEqual(resp.data, {"error": "Invalid credentials."})

        # 2 more attempts hit the 5/minute cap; 6th must be throttled with 429
        for _ in range(2):
            resp = self.client.post(url, cases[2], format="json")
            self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        throttled = self.client.post(url, cases[2], format="json")
        self.assertEqual(throttled.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    # Check #9 & #15: Security Headers, Cookie Hardening & Canonical UTC Settings
    def test_security_and_timezone_settings_enforced(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertTrue(settings.USE_TZ)
        self.assertEqual(settings.TIME_ZONE, "UTC")
        self.assertEqual(settings.DISPLAY_TIME_ZONE, "Africa/Lagos")


class BranchScopedWebSocketAuthorizationTests(TransactionTestCase):
    """
    Check #3: Verify that branch managers ONLY receive real-time 1–2★ alerts
    for their assigned branches and cannot eavesdrop on sibling branches,
    while Organization Admins receive alerts for all branches in their org.
    """

    def setUp(self):
        self.org = Organization.objects.create(name="ScopedMart", slug="scopedmart", is_active=True)
        self.branch_lekki = Branch.objects.create(organization=self.org, name="Lekki", is_active=True)
        self.branch_ikeja = Branch.objects.create(organization=self.org, name="Ikeja", is_active=True)

        self.admin = User.objects.create_user(
            organization=self.org,
            email="admin@scopedmart.ng",
            password="Password123!",
            role=User.Role.ADMIN,
        )
        self.lekki_mgr = User.objects.create_user(
            organization=self.org,
            email="lekki@scopedmart.ng",
            password="Password123!",
            role=User.Role.MANAGER,
        )
        UserBranch.objects.create(user=self.lekki_mgr, branch=self.branch_lekki)

    def test_branch_manager_isolated_from_unassigned_branch_alerts(self):
        async def _run():
            mgr_comm = WebsocketCommunicator(ManagerAlertConsumer.as_asgi(), "/ws/alerts/manager/")
            mgr_comm.scope["user"] = self.lekki_mgr

            admin_comm = WebsocketCommunicator(ManagerAlertConsumer.as_asgi(), "/ws/alerts/manager/")
            admin_comm.scope["user"] = self.admin

            mgr_ok, _ = await mgr_comm.connect()
            admin_ok, _ = await admin_comm.connect()
            self.assertTrue(mgr_ok)
            self.assertTrue(admin_ok)

            channel_layer = get_channel_layer()

            # Simulate 1-star alert at Ikeja (Lekki manager is NOT assigned to Ikeja)
            ikeja_event = {
                "type": "negative_feedback_alert",
                "content": {
                    "event": "negative_feedback_alert",
                    "branch_id": str(self.branch_ikeja.id),
                    "branch_name": "Ikeja",
                    "rating": 1,
                },
            }
            await channel_layer.group_send(f"org_{self.org.id}_alerts", ikeja_event)
            await channel_layer.group_send(f"branch_{self.branch_ikeja.id}_alerts", ikeja_event)

            # Admin receives Ikeja alert
            admin_msg = await admin_comm.receive_json_from(timeout=2)
            self.assertEqual(admin_msg["branch_name"], "Ikeja")

            # Lekki manager receives NOTHING for Ikeja
            self.assertTrue(await mgr_comm.receive_nothing(timeout=0.3))

            # Now simulate 1-star alert at Lekki -> BOTH Lekki manager and Admin receive it
            lekki_event = {
                "type": "negative_feedback_alert",
                "content": {
                    "event": "negative_feedback_alert",
                    "branch_id": str(self.branch_lekki.id),
                    "branch_name": "Lekki",
                    "rating": 1,
                },
            }
            await channel_layer.group_send(f"org_{self.org.id}_alerts", lekki_event)
            await channel_layer.group_send(f"branch_{self.branch_lekki.id}_alerts", lekki_event)

            mgr_msg = await mgr_comm.receive_json_from(timeout=2)
            self.assertEqual(mgr_msg["branch_name"], "Lekki")
            admin_msg2 = await admin_comm.receive_json_from(timeout=2)
            self.assertEqual(admin_msg2["branch_name"], "Lekki")

            await mgr_comm.disconnect()
            await admin_comm.disconnect()

        asyncio.run(_run())
