import uuid

from django.test import TestCase

from accounts.models import User
from audit.models import AuditLog
from complaints.models import Complaint
from feedback.models import Category, Feedback
from organizations.models import Branch, Organization


class TenantManagerTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(name="Org A", slug="org-a")
        self.org_b = Organization.objects.create(name="Org B", slug="org-b")

        self.branch_a = Branch.objects.create(organization=self.org_a, name="Branch A1")
        self.branch_b = Branch.objects.create(organization=self.org_b, name="Branch B1")

        self.category = Category.objects.create(name="Customer Service")

        self.user_a = User.objects.create(
            organization=self.org_a, email="user.a@org-a.com", password="x"
        )
        self.user_b = User.objects.create(
            organization=self.org_b, email="user.b@org-b.com", password="x"
        )

        self.feedback_a = Feedback.objects.create(
            branch=self.branch_a,
            organization=self.org_a,
            category=self.category,
            rating=4,
            message="Great service at Org A",
        )
        self.feedback_b = Feedback.objects.create(
            branch=self.branch_b,
            organization=self.org_b,
            category=self.category,
            rating=2,
            message="Slow checkout at Org B",
        )

        self.complaint_a = Complaint.objects.create(
            feedback=self.feedback_a,
            branch=self.branch_a,
            organization=self.org_a,
            created_by=self.user_a,
        )
        self.complaint_b = Complaint.objects.create(
            feedback=self.feedback_b,
            branch=self.branch_b,
            organization=self.org_b,
            created_by=self.user_b,
        )

        self.audit_a = AuditLog.objects.create(
            organization=self.org_a,
            actor_user=self.user_a,
            entity_type="Complaint",
            entity_id=self.complaint_a.id,
            action="created",
        )
        self.audit_b = AuditLog.objects.create(
            organization=self.org_b,
            actor_user=self.user_b,
            entity_type="Complaint",
            entity_id=self.complaint_b.id,
            action="created",
        )

    def test_branch_for_organization(self):
        # By Organization model instance
        qs_a = Branch.objects.for_organization(self.org_a)
        self.assertEqual(list(qs_a), [self.branch_a])

        # By UUID / string ID
        qs_b = Branch.objects.for_organization(str(self.org_b.id))
        self.assertEqual(list(qs_b), [self.branch_b])

    def test_feedback_for_organization_and_chaining(self):
        # QuerySet chaining: filter().for_organization()
        qs_a = Feedback.objects.filter(rating__gte=3).for_organization(self.org_a)
        self.assertEqual(list(qs_a), [self.feedback_a])

        # QuerySet chaining: for_organization().filter()
        qs_b = Feedback.objects.for_organization(self.org_b).filter(rating__lte=3)
        self.assertEqual(list(qs_b), [self.feedback_b])

        # Verify Org A query does not return Org B records
        self.assertNotIn(self.feedback_b, Feedback.objects.for_organization(self.org_a))

    def test_complaint_for_organization(self):
        qs_a = Complaint.objects.for_organization(self.org_a)
        self.assertEqual(list(qs_a), [self.complaint_a])

        qs_b = Complaint.objects.for_organization(self.org_b)
        self.assertEqual(list(qs_b), [self.complaint_b])

    def test_audit_log_for_organization(self):
        qs_a = AuditLog.objects.for_organization(self.org_a)
        self.assertEqual(list(qs_a), [self.audit_a])

        qs_b = AuditLog.objects.for_organization(self.org_b)
        self.assertEqual(list(qs_b), [self.audit_b])

    def test_for_organization_with_empty_or_other_org(self):
        other_org = Organization.objects.create(name="Empty Org", slug="empty-org")
        self.assertEqual(Branch.objects.for_organization(other_org).count(), 0)
        self.assertEqual(Feedback.objects.for_organization(other_org).count(), 0)
        self.assertEqual(Complaint.objects.for_organization(other_org).count(), 0)
        self.assertEqual(AuditLog.objects.for_organization(other_org).count(), 0)
