import asyncio
from datetime import timedelta
from unittest.mock import patch

from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditLog
from complaints.models import Complaint, ComplaintNote
from feedback.consumers import ManagerAlertConsumer
from feedback.models import Category, Feedback, QRCode
from organizations.models import Branch, Organization, Sector, UserBranch


class SectorDelegationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # Tenant A: FreshMart
        self.org_a = Organization.objects.create(name="FreshMart", slug="freshmart-test", is_active=True)
        self.branch_lekki = Branch.objects.create(organization=self.org_a, name="Lekki Phase 1", is_active=True)
        self.branch_ikeja = Branch.objects.create(organization=self.org_a, name="Ikeja City Mall", is_active=True)

        self.admin_a = User.objects.create_user(
            organization=self.org_a,
            email="admin@freshmart.test",
            password="Password123!",
            role=User.Role.ADMIN,
            full_name="COO Admin",
        )
        self.lekki_gm = User.objects.create_user(
            organization=self.org_a,
            email="gm.lekki@freshmart.test",
            password="Password123!",
            role=User.Role.MANAGER,
            full_name="Lekki GM",
        )
        UserBranch.objects.create(
            user=self.lekki_gm,
            branch=self.branch_lekki,
            sector=Sector.GENERAL,
            is_sector_lead=True,
        )

        # Bakery sector staff (non-lead) + sector lead at Lekki
        self.lekki_bakery_staff = User.objects.create_user(
            organization=self.org_a,
            email="baker.staff@freshmart.test",
            password="Password123!",
            role=User.Role.STAFF,
            full_name="Bakery Associate",
        )
        UserBranch.objects.create(
            user=self.lekki_bakery_staff,
            branch=self.branch_lekki,
            sector=Sector.BAKERY_PRODUCE,
            is_sector_lead=False,
        )

        self.lekki_bakery_lead = User.objects.create_user(
            organization=self.org_a,
            email="bakery.lead@freshmart.test",
            password="Password123!",
            role=User.Role.MANAGER,
            full_name="Chioma Bakery Lead",
        )
        UserBranch.objects.create(
            user=self.lekki_bakery_lead,
            branch=self.branch_lekki,
            sector=Sector.BAKERY_PRODUCE,
            is_sector_lead=True,
        )

        self.lekki_coldchain_lead = User.objects.create_user(
            organization=self.org_a,
            email="coldchain.lead@freshmart.test",
            password="Password123!",
            role=User.Role.MANAGER,
            full_name="Ibrahim Cold Chain Lead",
        )
        UserBranch.objects.create(
            user=self.lekki_coldchain_lead,
            branch=self.branch_lekki,
            sector=Sector.COLD_CHAIN_MEAT,
            is_sector_lead=True,
        )

        # Ikeja-only manager
        self.ikeja_mgr = User.objects.create_user(
            organization=self.org_a,
            email="mgr.ikeja@freshmart.test",
            password="Password123!",
            role=User.Role.MANAGER,
            full_name="Ikeja Manager",
        )
        UserBranch.objects.create(
            user=self.ikeja_mgr,
            branch=self.branch_ikeja,
            sector=Sector.GENERAL,
            is_sector_lead=True,
        )

        # Tenant B: Rival Supermarket
        self.org_b = Organization.objects.create(name="RivalMart", slug="rivalmart-test", is_active=True)
        self.branch_b = Branch.objects.create(organization=self.org_b, name="Abuja Flagship", is_active=True)
        self.mgr_b = User.objects.create_user(
            organization=self.org_b,
            email="mgr@rivalmart.test",
            password="Password123!",
            role=User.Role.MANAGER,
            full_name="Rival Manager",
        )
        UserBranch.objects.create(
            user=self.mgr_b,
            branch=self.branch_b,
            sector=Sector.BAKERY_PRODUCE,
            is_sector_lead=True,
        )

        # Sector-mapped categories & QR
        self.cat_bakery = Category.objects.create(
            name="Bakery & Fresh Produce",
            organization=self.org_a,
            default_sector=Sector.BAKERY_PRODUCE,
        )
        self.cat_pos = Category.objects.create(
            name="Cashier Speed",
            organization=None,
            default_sector=Sector.POS_CASHIER,
        )
        self.qr_lekki = QRCode.objects.create(branch=self.branch_lekki, is_active=True)

        # Base complaint at Lekki
        self.fb_lekki = Feedback.objects.create(
            organization=self.org_a,
            branch=self.branch_lekki,
            category=self.cat_bakery,
            rating=1,
            message="Sourdough loaf was burnt.",
        )
        self.complaint_lekki = Complaint.objects.create(
            feedback=self.fb_lekki,
            organization=self.org_a,
            branch=self.branch_lekki,
            sector=Sector.GENERAL,
            priority=Complaint.Priority.MEDIUM,
            status=Complaint.Status.NEW,
            created_by=self.admin_a,
        )

    def tearDown(self):
        cache.clear()

    # 1. Sector Manager Roster Lookup
    def test_delegates_roster_scoped_to_org_and_branch_with_sector_metadata(self):
        self.client.force_authenticate(user=self.lekki_gm)
        url = reverse("complaint-delegates")

        resp = self.client.get(f"{url}?branch_id={self.branch_lekki.id}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        delegates = resp.data["delegates"]
        emails = {d["email"] for d in delegates}
        self.assertIn("bakery.lead@freshmart.test", emails)
        self.assertIn("coldchain.lead@freshmart.test", emails)
        self.assertNotIn("mgr.ikeja@freshmart.test", emails)
        self.assertNotIn("mgr@rivalmart.test", emails)

        bakery_entry = next(d for d in delegates if d["email"] == "bakery.lead@freshmart.test")
        self.assertEqual(bakery_entry["sector"], Sector.BAKERY_PRODUCE)
        self.assertEqual(bakery_entry["sector_label"], "Bakery & Fresh Produce")
        self.assertTrue(bakery_entry["is_sector_lead"])

        # Lekki GM cannot query delegates for Ikeja branch
        resp_forbidden = self.client.get(f"{url}?branch_id={self.branch_ikeja.id}")
        self.assertEqual(resp_forbidden.status_code, status.HTTP_403_FORBIDDEN)

        # Lekki GM cannot query delegates for Tenant B
        resp_tenant_b = self.client.get(f"{url}?branch_id={self.branch_b.id}")
        self.assertEqual(resp_tenant_b.status_code, status.HTTP_403_FORBIDDEN)

    # 2. Task Delegation, Pessimistic Locking, Notes, AuditLog & WebSocket on_commit
    def test_delegate_complaint_updates_fields_creates_note_audit_and_ws_alert(self):
        self.client.force_authenticate(user=self.lekki_gm)
        url = reverse("complaint-delegate", kwargs={"id": self.complaint_lekki.id})
        due = (timezone.now() + timedelta(hours=4)).replace(microsecond=0)
        channel_layer = get_channel_layer()

        payload = {
            "assigned_to_id": str(self.lekki_coldchain_lead.id),
            "sector": Sector.COLD_CHAIN_MEAT,
            "priority": "URGENT",
            "due_at": due.isoformat(),
            "note": "Inspect cold room thermometer on Aisle 4 and call customer.",
        }

        with patch.object(
            Complaint.objects, "select_for_update", wraps=Complaint.objects.select_for_update
        ) as mock_sfu:
            with patch.object(channel_layer, "group_send") as mock_send:
                with self.captureOnCommitCallbacks(execute=True):
                    resp = self.client.post(url, payload, format="json")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        mock_sfu.assert_called_once()

        self.complaint_lekki.refresh_from_db()
        self.assertEqual(self.complaint_lekki.assigned_to_id, self.lekki_coldchain_lead.id)
        self.assertEqual(self.complaint_lekki.sector, Sector.COLD_CHAIN_MEAT)
        self.assertEqual(self.complaint_lekki.priority, Complaint.Priority.URGENT)
        self.assertEqual(self.complaint_lekki.status, Complaint.Status.IN_PROGRESS)
        self.assertEqual(self.complaint_lekki.delegated_by_id, self.lekki_gm.id)
        self.assertIsNotNone(self.complaint_lekki.delegated_at)
        self.assertIsNotNone(self.complaint_lekki.due_at)

        # Delegation note appended
        note = ComplaintNote.objects.filter(complaint=self.complaint_lekki).last()
        self.assertIsNotNone(note)
        self.assertIn("[DELEGATED to Ibrahim Cold Chain Lead", note.body)
        self.assertIn("Inspect cold room thermometer on Aisle 4", note.body)

        # Immutable AuditLog entry written
        self.assertTrue(
            AuditLog.objects.filter(
                organization=self.org_a,
                actor_user=self.lekki_gm,
                entity_type="Complaint",
                entity_id=self.complaint_lekki.id,
                action="complaint.delegated",
            ).exists()
        )

        # Real-time WebSocket delegation alert dispatched to org + branch groups
        self.assertEqual(mock_send.call_count, 2)
        sent_groups = [c.args[0] for c in mock_send.call_args_list]
        self.assertIn(f"org_{self.org_a.id}_alerts", sent_groups)
        self.assertIn(f"branch_{self.branch_lekki.id}_alerts", sent_groups)
        ws_event = mock_send.call_args_list[0].args[1]
        self.assertEqual(ws_event["type"], "send_task_delegated_alert")
        self.assertEqual(ws_event["content"]["event_type"], "TASK_DELEGATED")
        self.assertEqual(ws_event["content"]["assigned_to_id"], str(self.lekki_coldchain_lead.id))

    # 3. Cross-Branch & Cross-Tenant Delegation Rejection
    def test_cross_branch_and_cross_tenant_delegation_rejected(self):
        self.client.force_authenticate(user=self.admin_a)
        url = reverse("complaint-delegate", kwargs={"id": self.complaint_lekki.id})

        # Delegating Lekki complaint to Ikeja-only manager -> 400
        resp_cross_branch = self.client.post(
            url,
            {"assigned_to_id": str(self.ikeja_mgr.id), "sector": Sector.GENERAL},
            format="json",
        )
        self.assertEqual(resp_cross_branch.status_code, status.HTTP_400_BAD_REQUEST)

        # Delegating Lekki complaint to Tenant B manager -> 400
        resp_cross_tenant = self.client.post(
            url,
            {"assigned_to_id": str(self.mgr_b.id), "sector": Sector.BAKERY_PRODUCE},
            format="json",
        )
        self.assertEqual(resp_cross_tenant.status_code, status.HTTP_400_BAD_REQUEST)

    # 4. Role Permission Enforcement
    def test_staff_cannot_delegate_while_manager_and_admin_succeed(self):
        url = reverse("complaint-delegate", kwargs={"id": self.complaint_lekki.id})
        payload = {
            "assigned_to_id": str(self.lekki_bakery_lead.id),
            "sector": Sector.BAKERY_PRODUCE,
            "priority": "HIGH",
        }

        # STAFF -> 403 Forbidden
        self.client.force_authenticate(user=self.lekki_bakery_staff)
        resp_staff = self.client.post(url, payload, format="json")
        self.assertEqual(resp_staff.status_code, status.HTTP_403_FORBIDDEN)

        # ADMIN -> 200 OK
        self.client.force_authenticate(user=self.admin_a)
        resp_admin = self.client.post(url, payload, format="json")
        self.assertEqual(resp_admin.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_admin.data["assigned_to_email"], "bakery.lead@freshmart.test")

    # 5. Auto-Routing on 1–2★ Public QR Submission
    def test_public_1_star_bakery_submission_auto_routes_to_bakery_sector_lead(self):
        channel_layer = get_channel_layer()
        url = reverse("public-feedback-submit", kwargs={"token": self.qr_lekki.token})
        payload = {
            "rating": 1,
            "category": str(self.cat_bakery.id),
            "message": "Croissants were moldy!",
            "customer_name": "Nkechi",
        }

        with patch.object(channel_layer, "group_send") as mock_send:
            with self.captureOnCommitCallbacks(execute=True):
                resp = self.client.post(url, payload, format="json")

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("complaint_id", resp.data)
        self.assertEqual(resp.data["routed_sector"], Sector.BAKERY_PRODUCE)
        self.assertEqual(resp.data["priority"], Complaint.Priority.URGENT)

        auto_complaint = Complaint.objects.get(id=resp.data["complaint_id"])
        self.assertEqual(auto_complaint.sector, Sector.BAKERY_PRODUCE)
        self.assertEqual(auto_complaint.priority, Complaint.Priority.URGENT)
        # Preferred the sector lead (Chioma) over the non-lead bakery staff member
        self.assertEqual(auto_complaint.assigned_to_id, self.lekki_bakery_lead.id)
        self.assertIsNone(auto_complaint.created_by)
        # WebSocket alert fired on commit
        self.assertEqual(mock_send.call_count, 2)

    def test_public_5_star_submission_does_not_auto_create_complaint(self):
        url = reverse("public-feedback-submit", kwargs={"token": self.qr_lekki.token})
        resp = self.client.post(
            url,
            {
                "rating": 5,
                "category": str(self.cat_bakery.id),
                "message": "Best fresh bread in Lekki!",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("complaint_id", resp.data)
        self.assertFalse(Complaint.objects.filter(feedback_id=resp.data["id"]).exists())

    # 6. Sector & assigned_to_me Queue Filtering
    def test_complaint_list_filters_by_sector_and_assigned_to_me(self):
        # Assign existing complaint to bakery lead in BAKERY_PRODUCE
        self.complaint_lekki.sector = Sector.BAKERY_PRODUCE
        self.complaint_lekki.assigned_to = self.lekki_bakery_lead
        self.complaint_lekki.priority = Complaint.Priority.URGENT
        self.complaint_lekki.save()

        # Create second complaint assigned to cold chain lead
        fb2 = Feedback.objects.create(
            organization=self.org_a,
            branch=self.branch_lekki,
            category=self.cat_pos,
            rating=2,
            message="Dairy chiller warm.",
        )
        Complaint.objects.create(
            feedback=fb2,
            organization=self.org_a,
            branch=self.branch_lekki,
            sector=Sector.COLD_CHAIN_MEAT,
            priority=Complaint.Priority.HIGH,
            assigned_to=self.lekki_coldchain_lead,
            created_by=self.admin_a,
        )

        self.client.force_authenticate(user=self.lekki_bakery_lead)
        url = reverse("complaint-list-create")

        resp = self.client.get(f"{url}?sector=BAKERY_PRODUCE&assigned_to_me=true")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], str(self.complaint_lekki.id))
        self.assertEqual(results[0]["sector"], Sector.BAKERY_PRODUCE)

        # Cold chain sector + assigned_to_me=true returns 0 for bakery lead
        resp_empty = self.client.get(f"{url}?sector=COLD_CHAIN_MEAT&assigned_to_me=true")
        empty_results = resp_empty.data["results"] if isinstance(resp_empty.data, dict) else resp_empty.data
        self.assertEqual(len(empty_results), 0)


class TaskDelegationWebSocketTests(TransactionTestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="WS Delegation Mart", slug="ws-del-mart", is_active=True)
        self.branch = Branch.objects.create(organization=self.org, name="Lekki", is_active=True)
        self.sector_lead = User.objects.create_user(
            organization=self.org,
            email="bakery.ws@del.ng",
            password="Password123!",
            role=User.Role.MANAGER,
            full_name="Bakery WS Lead",
        )
        UserBranch.objects.create(
            user=self.sector_lead,
            branch=self.branch,
            sector=Sector.BAKERY_PRODUCE,
            is_sector_lead=True,
        )

    def test_sector_manager_receives_live_task_delegated_websocket_alert(self):
        async def _run():
            communicator = WebsocketCommunicator(
                ManagerAlertConsumer.as_asgi(), "/ws/alerts/manager/"
            )
            communicator.scope["user"] = self.sector_lead

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            channel_layer = get_channel_layer()
            await channel_layer.group_send(
                f"branch_{self.branch.id}_alerts",
                {
                    "type": "send_task_delegated_alert",
                    "content": {
                        "event_type": "TASK_DELEGATED",
                        "complaint_id": "test-id",
                        "branch_id": str(self.branch.id),
                        "branch_name": "Lekki",
                        "sector": Sector.BAKERY_PRODUCE,
                        "sector_label": "Bakery & Fresh Produce",
                        "priority": "urgent",
                        "assigned_to_id": str(self.sector_lead.id),
                        "assigned_to_name": "Bakery WS Lead",
                        "delegated_by_name": "COO Admin",
                        "note": "Check ovens immediately",
                    },
                },
            )

            msg = await communicator.receive_json_from(timeout=2)
            self.assertEqual(msg["event_type"], "TASK_DELEGATED")
            self.assertEqual(msg["sector"], Sector.BAKERY_PRODUCE)
            self.assertEqual(msg["priority"], "urgent")
            await communicator.disconnect()

        asyncio.run(_run())
