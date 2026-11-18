import asyncio
import io
from datetime import timedelta
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from feedback.consumers import ManagerAlertConsumer
from feedback.models import Category, Feedback
from organizations.models import Branch, Organization, UserBranch


class ExecutivePDFReportTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Tenant A
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

        # Tenant B
        self.org_b = Organization.objects.create(name="Supermarket B", slug="org-b", is_active=True)
        self.branch_b1 = Branch.objects.create(organization=self.org_b, name="Branch B1", is_active=True)

        self.category = Category.objects.create(name="General Feedback", organization=None)

        # Seed some feedback
        Feedback.objects.create(
            organization=self.org_a,
            branch=self.branch_a1,
            category=self.category,
            rating=5,
            message="Great cashier!",
            customer_name="Alice",
        )
        Feedback.objects.create(
            organization=self.org_a,
            branch=self.branch_a1,
            category=self.category,
            rating=1,
            message="Long checkout lines.",
            customer_name="Bob",
        )

        self.url = reverse("executive-pdf-report")

    def test_executive_pdf_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_executive_pdf_rejects_user_without_organization(self):
        user_no_org = User(
            id=uuid4(),
            email="noorg@example.com",
            role=User.Role.STAFF,
        )
        self.client.force_authenticate(user=user_no_org)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("must belong to an organization", str(response.data))

    def test_admin_generates_valid_pdf_report(self):
        self.client.force_authenticate(user=self.admin_a)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("Executive_Feedback_Report_", response["Content-Disposition"])
        # Verify valid PDF header
        self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_manager_scoped_to_assigned_branch(self):
        self.client.force_authenticate(user=self.manager_a1)
        response = self.client.get(f"{self.url}?branch_id={self.branch_a1.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_manager_forbidden_from_unassigned_branch(self):
        self.client.force_authenticate(user=self.manager_a1)
        # Attempt to export branch A2 which manager is not assigned to
        response = self.client.get(f"{self.url}?branch_id={self.branch_a2.id}")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("do not have permission", str(response.data))

    def test_manager_forbidden_from_other_tenant_branch(self):
        self.client.force_authenticate(user=self.manager_a1)
        # Attempt to export branch B1 from Tenant B
        response = self.client.get(f"{self.url}?branch_id={self.branch_b1.id}")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_branch_uuid_rejected(self):
        self.client.force_authenticate(user=self.admin_a)
        response = self.client.get(f"{self.url}?branch_id=not-a-valid-uuid")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_date_filters_accepted_and_generate_pdf(self):
        self.client.force_authenticate(user=self.admin_a)
        today = timezone.now().strftime("%Y-%m-%d")
        response = self.client.get(f"{self.url}?start_date={today}&end_date={today}&days=7")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b"%PDF-"))


class NegativeFeedbackWebSocketBroadcastTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Store Org", slug="store-org", is_active=True)
        self.branch = Branch.objects.create(organization=self.org, name="Downtown Branch", is_active=True)
        self.category = Category.objects.create(name="Customer Service", organization=self.org)

    def test_negative_feedback_broadcasts_to_channel_layer(self):
        channel_layer = get_channel_layer()
        self.assertIsNotNone(channel_layer)

        with patch.object(channel_layer, "group_send") as mock_group_send:
            with self.captureOnCommitCallbacks(execute=True):
                fb = Feedback.objects.create(
                    organization=self.org,
                    branch=self.branch,
                    category=self.category,
                    rating=2,
                    message="Cold soup and slow service.",
                    customer_name="Jane Doe",
                )

            mock_group_send.assert_called_once()
            group_name, payload = mock_group_send.call_args[0]
            self.assertEqual(group_name, f"org_{self.org.id}_alerts")
            self.assertEqual(payload["type"], "negative_feedback_alert")
            content = payload["content"]
            self.assertEqual(content["rating"], 2)
            self.assertEqual(content["sentiment"], Feedback.Sentiment.NEGATIVE)
            self.assertEqual(content["message"], "Cold soup and slow service.")
            self.assertEqual(content["customer_name"], "Jane Doe")
            self.assertEqual(content["branch_name"], "Downtown Branch")
            self.assertEqual(content["id"], str(fb.id))

    def test_positive_feedback_does_not_broadcast(self):
        channel_layer = get_channel_layer()
        self.assertIsNotNone(channel_layer)

        with patch.object(channel_layer, "group_send") as mock_group_send:
            with self.captureOnCommitCallbacks(execute=True):
                Feedback.objects.create(
                    organization=self.org,
                    branch=self.branch,
                    category=self.category,
                    rating=4,
                    message="Very good experience.",
                    customer_name="Happy Customer",
                )
            mock_group_send.assert_not_called()

    def test_neutral_feedback_does_not_broadcast(self):
        channel_layer = get_channel_layer()
        self.assertIsNotNone(channel_layer)

        with patch.object(channel_layer, "group_send") as mock_group_send:
            with self.captureOnCommitCallbacks(execute=True):
                Feedback.objects.create(
                    organization=self.org,
                    branch=self.branch,
                    category=self.category,
                    rating=3,
                    message="Average shopping experience.",
                )
            mock_group_send.assert_not_called()

    def test_feedback_update_does_not_retrigger_broadcast(self):
        channel_layer = get_channel_layer()
        self.assertIsNotNone(channel_layer)

        with self.captureOnCommitCallbacks(execute=True):
            fb = Feedback.objects.create(
                organization=self.org,
                branch=self.branch,
                category=self.category,
                rating=5,
                message="Top quality.",
            )

        with patch.object(channel_layer, "group_send") as mock_group_send:
            with self.captureOnCommitCallbacks(execute=True):
                fb.rating = 1
                fb.message = "Actually it broke right away."
                fb.save()
            # Since is_new is False on updates, broadcast is NOT fired
            mock_group_send.assert_not_called()

    def test_websocket_consumer_rejects_unauthenticated(self):
        async def _run():
            communicator = WebsocketCommunicator(ManagerAlertConsumer.as_asgi(), "/ws/alerts/manager/")
            communicator.scope["user"] = AnonymousUser()
            connected, _ = await communicator.connect()
            self.assertFalse(connected)
        asyncio.run(_run())

    def test_websocket_consumer_rejects_user_without_org(self):
        async def _run():
            communicator = WebsocketCommunicator(ManagerAlertConsumer.as_asgi(), "/ws/alerts/manager/")
            user = Mock(is_authenticated=True, organization_id=None)
            communicator.scope["user"] = user
            connected, _ = await communicator.connect()
            self.assertFalse(connected)
        asyncio.run(_run())

    def test_websocket_consumer_accepts_and_receives_alert(self):
        async def _run():
            org_id = uuid4()
            communicator = WebsocketCommunicator(ManagerAlertConsumer.as_asgi(), "/ws/alerts/manager/")
            user = Mock(is_authenticated=True, organization_id=org_id)
            communicator.scope["user"] = user

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Send event to the group
            channel_layer = get_channel_layer()
            test_payload = {
                "event": "negative_feedback_alert",
                "rating": 1,
                "message": "Out of stock on milk",
                "branch_name": "Lekki Branch",
            }
            await channel_layer.group_send(
                f"org_{org_id}_alerts",
                {
                    "type": "negative_feedback_alert",
                    "content": test_payload,
                },
            )

            response = await communicator.receive_json_from()
            self.assertEqual(response["event"], "negative_feedback_alert")
            self.assertEqual(response["rating"], 1)
            self.assertEqual(response["message"], "Out of stock on milk")

            await communicator.disconnect()
        asyncio.run(_run())
