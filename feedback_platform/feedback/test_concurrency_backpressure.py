import asyncio
from unittest.mock import patch

from channels.exceptions import ChannelFull
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditLog
from complaints.models import Complaint
from feedback.consumers import ManagerAlertConsumer
from feedback.models import Category, Feedback, QRCode
from organizations.models import Branch, Organization, UserBranch


class ConcurrencyAndBackpressureTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        self.org = Organization.objects.create(
            name="FreshMart High-Volume",
            slug="freshmart-hv",
            is_active=True,
        )
        self.branch = Branch.objects.create(
            organization=self.org,
            name="Victoria Island Flagship",
            is_active=True,
        )
        self.branch_2 = Branch.objects.create(
            organization=self.org,
            name="Ikoyi Express",
            is_active=True,
        )
        self.category = Category.objects.create(
            name="Checkout Speed",
            organization=None,
            is_active=True,
        )
        self.qr = QRCode.objects.create(branch=self.branch, is_active=True)

        self.admin = User.objects.create_user(
            organization=self.org,
            email="admin@freshmart-hv.ng",
            password="Password123!",
            role=User.Role.ADMIN,
        )
        self.manager = User.objects.create_user(
            organization=self.org,
            email="manager@freshmart-hv.ng",
            password="Password123!",
            role=User.Role.MANAGER,
        )
        UserBranch.objects.create(user=self.manager, branch=self.branch)

    def tearDown(self):
        cache.clear()

    # ------------------------------------------------------------------
    # 1. Graceful Redis Degradation (ChannelFull, ConnectionError, TimeoutError)
    # ------------------------------------------------------------------
    def test_public_submit_succeeds_on_channel_full_backpressure(self):
        channel_layer = get_channel_layer()
        url = reverse("public-feedback-submit", kwargs={"token": self.qr.token})
        payload = {
            "rating": 1,
            "category": str(self.category.id),
            "message": "POS terminals down during rush hour!",
            "customer_name": "Chinedu",
        }

        with patch.object(
            channel_layer, "group_send", side_effect=ChannelFull("Queue at capacity 500")
        ) as mock_send:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_send.assert_called_once()
        self.assertTrue(
            Feedback.objects.filter(
                id=response.data["id"],
                organization=self.org,
                branch=self.branch,
                rating=1,
            ).exists()
        )

    def test_public_submit_succeeds_on_redis_connection_error(self):
        channel_layer = get_channel_layer()
        url = reverse("public-feedback-submit", kwargs={"token": self.qr.token})
        payload = {
            "rating": 2,
            "category": str(self.category.id),
            "message": "Long queue at counter 4.",
            "customer_name": "Amaka",
        }

        with patch.object(
            channel_layer, "group_send", side_effect=ConnectionError("Redis unreachable")
        ) as mock_send:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_send.assert_called_once()
        self.assertTrue(Feedback.objects.filter(id=response.data["id"]).exists())

    def test_public_submit_succeeds_on_broadcast_timeout(self):
        channel_layer = get_channel_layer()
        url = reverse("public-feedback-submit", kwargs={"token": self.qr.token})
        payload = {
            "rating": 1,
            "category": str(self.category.id),
            "message": "Expired dairy item on shelf.",
        }

        with patch.object(
            channel_layer, "group_send", side_effect=TimeoutError("Redis jitter timeout")
        ) as mock_send:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_send.assert_called_once()
        self.assertTrue(Feedback.objects.filter(id=response.data["id"]).exists())

    # ------------------------------------------------------------------
    # 2. Transaction Commit Ordering (No Phantom Alerts on Rollback)
    # ------------------------------------------------------------------
    def test_websocket_broadcast_does_not_fire_when_transaction_rolls_back(self):
        channel_layer = get_channel_layer()

        with patch.object(channel_layer, "group_send") as mock_send:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                try:
                    with transaction.atomic():
                        Feedback.objects.create(
                            organization=self.org,
                            branch=self.branch,
                            category=self.category,
                            rating=1,
                            message="Should roll back and never broadcast!",
                        )
                        raise RuntimeError("Simulated DB failure after insert")
                except RuntimeError:
                    pass

        # Transaction rolled back: no row persisted, no on_commit callbacks executed, no WS alert sent
        self.assertEqual(Feedback.objects.count(), 0)
        self.assertEqual(len(callbacks), 0)
        mock_send.assert_not_called()

    def test_websocket_broadcast_fires_only_after_commit(self):
        channel_layer = get_channel_layer()

        with patch.object(channel_layer, "group_send") as mock_send:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                Feedback.objects.create(
                    organization=self.org,
                    branch=self.branch,
                    category=self.category,
                    rating=1,
                    message="Committed critical review",
                )
                # Before commit executes, group_send has NOT been called yet
                mock_send.assert_not_called()

            # Simulate transaction commit executing registered callbacks
            for cb in callbacks:
                cb()

            mock_send.assert_called_once()
            group_name, payload = mock_send.call_args[0]
            self.assertEqual(group_name, f"org_{self.org.id}_alerts")
            self.assertEqual(payload["content"]["rating"], 1)

    # ------------------------------------------------------------------
    # 3. Idempotent Atomic QR Rotation with Row-Level Locking
    # ------------------------------------------------------------------
    def test_rapid_qr_rotations_preserve_single_active_constraint(self):
        seen_tokens = {self.qr.token}

        for _ in range(15):
            new_qr = QRCode.rotate_for_branch(self.branch)
            self.assertTrue(new_qr.is_active)
            self.assertNotIn(new_qr.token, seen_tokens)
            seen_tokens.add(new_qr.token)

            active_count = QRCode.objects.filter(branch=self.branch, is_active=True).count()
            self.assertEqual(active_count, 1)

        total_count = QRCode.objects.filter(branch=self.branch).count()
        revoked_count = QRCode.objects.filter(
            branch=self.branch, is_active=False, revoked_at__isnull=False
        ).count()
        self.assertEqual(total_count, 16)
        self.assertEqual(revoked_count, 15)

    def test_qr_rotation_acquires_select_for_update_on_branch(self):
        with patch.object(
            Branch.objects, "select_for_update", wraps=Branch.objects.select_for_update
        ) as mock_sfu:
            QRCode.rotate_for_branch(self.branch)
            mock_sfu.assert_called_once()

    # ------------------------------------------------------------------
    # 4. Stampede-Proof Analytics Caching & Version Invalidation
    # ------------------------------------------------------------------
    def test_manager_analytics_executes_only_one_aggregation_while_cache_warm(self):
        Feedback.objects.create(
            organization=self.org,
            branch=self.branch,
            category=self.category,
            rating=5,
            message="Fast and clean!",
        )
        Feedback.objects.create(
            organization=self.org,
            branch=self.branch,
            category=self.category,
            rating=2,
            message="Slow bakery line.",
        )

        self.client.force_authenticate(user=self.manager)
        url = reverse("manager-analytics-overview")

        with CaptureQueriesContext(connection) as ctx:
            for _ in range(6):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, status.HTTP_200_OK)
                self.assertEqual(resp.data["summary"]["total_feedback"], 2)

        # Count how many SQL queries aggregated the `feedback` table
        feedback_agg_queries = [
            q["sql"] for q in ctx.captured_queries if '"feedback"' in q["sql"].lower() or " from feedback" in q["sql"].lower()
        ]
        self.assertEqual(len(feedback_agg_queries), 1)

    def test_analytics_stale_while_revalidate_during_lock_contention(self):
        Feedback.objects.create(
            organization=self.org,
            branch=self.branch,
            category=self.category,
            rating=4,
            message="Good store.",
        )

        self.client.force_authenticate(user=self.manager)
        url = reverse("manager-analytics-overview")

        # Warm the cache (sets both fresh key and :stale key)
        warm_resp = self.client.get(url)
        self.assertEqual(warm_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(warm_resp.data["summary"]["total_feedback"], 1)

        # Simulate fresh cache key expiry while stale snapshot remains, AND another worker holds the lock
        from feedback.cache import build_analytics_cache_key

        cache_key = build_analytics_cache_key(self.org.id, [self.branch.id], "", "")
        lock_key = f"{cache_key}:lock"
        cache.delete(cache_key)
        cache.set(lock_key, "1", timeout=5)  # Another worker currently holds single-flight lock

        with CaptureQueriesContext(connection) as ctx:
            contended_resp = self.client.get(url)

        self.assertEqual(contended_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(contended_resp.data["summary"]["total_feedback"], 1)
        # Zero aggregation queries hit the database because stale-while-revalidate served the request!
        feedback_agg_queries = [
            q["sql"] for q in ctx.captured_queries if '"feedback"' in q["sql"].lower() or " from feedback" in q["sql"].lower()
        ]
        self.assertEqual(len(feedback_agg_queries), 0)

    def test_analytics_cache_version_bumps_on_feedback_commit(self):
        self.client.force_authenticate(user=self.manager)
        url = reverse("manager-analytics-overview")

        # Initial empty analytics (cached)
        resp1 = self.client.get(url)
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        self.assertEqual(resp1.data["summary"]["total_feedback"], 0)

        # New feedback commits -> on_commit bumps cache version
        with self.captureOnCommitCallbacks(execute=True):
            Feedback.objects.create(
                organization=self.org,
                branch=self.branch,
                category=self.category,
                rating=5,
                message="Fresh submission!",
            )

        # Next analytics request immediately sees fresh count without waiting 60s
        resp2 = self.client.get(url)
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertEqual(resp2.data["summary"]["total_feedback"], 1)

    # ------------------------------------------------------------------
    # 5. Backpressure Settings & Complaint Row-Level Locking
    # ------------------------------------------------------------------
    def test_channel_layer_backpressure_settings_configured(self):
        cfg = settings.CHANNEL_LAYERS["default"]["CONFIG"]
        self.assertEqual(cfg["capacity"], 500)
        self.assertEqual(cfg["expiry"], 60)
        self.assertEqual(cfg["group_expiry"], 86400)

    def test_complaint_mutation_uses_select_for_update_and_audits_atomically(self):
        fb = Feedback.objects.create(
            organization=self.org,
            branch=self.branch,
            category=self.category,
            rating=1,
            message="Broken freezer aisle.",
        )
        complaint = Complaint.objects.create(
            feedback=fb,
            organization=self.org,
            branch=self.branch,
            status=Complaint.Status.NEW,
            priority=Complaint.Priority.HIGH,
            created_by=self.admin,
        )

        self.client.force_authenticate(user=self.manager)
        url = reverse("complaint-detail", kwargs={"id": complaint.id})

        with patch.object(
            Complaint.objects, "select_for_update", wraps=Complaint.objects.select_for_update
        ) as mock_sfu:
            resp = self.client.patch(
                url,
                {
                    "status": Complaint.Status.RESOLVED,
                    "resolution_summary": "Technician repaired compressor.",
                },
                format="json",
            )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        mock_sfu.assert_called_once()
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, Complaint.Status.RESOLVED)
        self.assertIsNotNone(complaint.resolved_at)
        self.assertTrue(
            AuditLog.objects.filter(
                entity_type="Complaint",
                entity_id=complaint.id,
                action="COMPLAINT_UPDATED",
            ).exists()
        )


class WebSocketBackpressureAndZombieTests(TransactionTestCase):
    """
    Uses TransactionTestCase so async `database_sync_to_async` queries run
    against committed rows without SQLite cross-thread table locks.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            name="FreshMart WS Tenant",
            slug="freshmart-ws",
            is_active=True,
        )
        self.manager = User.objects.create_user(
            organization=self.org,
            email="ws.manager@freshmart.ng",
            password="Password123!",
            role=User.Role.MANAGER,
        )

    def test_websocket_heartbeat_ping_pong_and_zombie_revocation(self):
        async def _run():
            communicator = WebsocketCommunicator(
                ManagerAlertConsumer.as_asgi(), "/ws/alerts/manager/"
            )
            communicator.scope["user"] = self.manager

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Heartbeat ping -> pong
            await communicator.send_json_to({"type": "ping"})
            pong = await communicator.receive_json_from()
            self.assertEqual(pong["type"], "pong")
            self.assertIn("timestamp", pong)

            # Deactivate manager mid-session (zombie connection)
            from channels.db import database_sync_to_async

            @database_sync_to_async
            def _deactivate():
                User.objects.filter(pk=self.manager.pk).update(is_active=False)

            await _deactivate()

            # Next heartbeat must detect zombie session and close socket
            await communicator.send_json_to({"type": "ping"})
            output = await communicator.receive_output(timeout=2)
            self.assertEqual(output["type"], "websocket.close")
            self.assertEqual(output["code"], 4003)

        asyncio.run(_run())

    def test_websocket_rejects_suspended_organization_on_connect(self):
        self.org.is_active = False
        self.org.save(update_fields=["is_active"])

        async def _run():
            communicator = WebsocketCommunicator(
                ManagerAlertConsumer.as_asgi(), "/ws/alerts/manager/"
            )
            communicator.scope["user"] = self.manager
            connected, code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(code, 4001)

        asyncio.run(_run())

    def test_websocket_blocks_alert_and_closes_when_org_suspended_mid_session(self):
        async def _run():
            communicator = WebsocketCommunicator(
                ManagerAlertConsumer.as_asgi(), "/ws/alerts/manager/"
            )
            communicator.scope["user"] = self.manager
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            from channels.db import database_sync_to_async

            @database_sync_to_async
            def _suspend_org():
                Organization.objects.filter(pk=self.org.pk).update(is_active=False)

            await _suspend_org()

            # Dispatch alert to group: consumer must NOT forward alert and must close socket
            channel_layer = get_channel_layer()
            await channel_layer.group_send(
                f"org_{self.org.id}_alerts",
                {
                    "type": "negative_feedback_alert",
                    "content": {"event": "negative_feedback_alert", "rating": 1},
                },
            )
            output = await communicator.receive_output(timeout=2)
            self.assertEqual(output["type"], "websocket.close")
            self.assertEqual(output["code"], 4003)

        asyncio.run(_run())
