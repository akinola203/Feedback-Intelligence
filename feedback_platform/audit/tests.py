import uuid

from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import PlatformAdmin, User
from audit.models import AuditLog
from organizations.models import Organization


class AuditLogTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org I", slug="org-i")
        self.user = User.objects.create(
            organization=self.org, email="staff@example.com", password="x",
            role=User.Role.STAFF,
        )
        self.admin = PlatformAdmin.objects.create(email="root@platform.com", password="x")

    def test_org_user_action_is_valid(self):
        AuditLog.objects.create(
            organization=self.org, actor_user=self.user,
            entity_type="Complaint", entity_id=uuid.uuid4(),
            action="status_changed",
        )

    def test_platform_admin_action_is_valid(self):
        AuditLog.objects.create(
            organization=self.org, actor_platform_admin=self.admin,
            entity_type="Organization", entity_id=self.org.id,
            action="organization_suspended",
        )

    def test_system_generated_entry_with_no_actor_is_valid(self):
        AuditLog.objects.create(
            organization=self.org, entity_type="Feedback",
            entity_id=uuid.uuid4(), action="sentiment_derived",
        )

    def test_both_actors_set_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AuditLog.objects.create(
                    organization=self.org,
                    actor_user=self.user,
                    actor_platform_admin=self.admin,
                    entity_type="Complaint", entity_id=uuid.uuid4(),
                    action="status_changed",
                )
