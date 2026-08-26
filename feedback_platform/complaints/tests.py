from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from complaints.models import Complaint
from feedback.models import Category, Feedback
from organizations.models import Branch, Organization


class ComplaintTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org H", slug="org-h")
        self.branch = Branch.objects.create(organization=self.org, name="Apapa")
        self.category = Category.objects.create(organization=None, name="Checkout")
        self.manager = User.objects.create(
            organization=self.org, email="mgr@example.com", password="x",
            role=User.Role.MANAGER,
        )
        self.feedback = Feedback.objects.create(
            branch=self.branch, category=self.category, rating=1,
            message="Charged twice for the same product.",
        )

    def test_complaint_derives_branch_and_org_from_feedback(self):
        complaint = Complaint.objects.create(
            feedback=self.feedback, created_by=self.manager,
        )
        self.assertEqual(complaint.branch_id, self.branch.id)
        self.assertEqual(complaint.organization_id, self.org.id)

    def test_feedback_can_have_at_most_one_complaint(self):
        Complaint.objects.create(feedback=self.feedback, created_by=self.manager)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Complaint.objects.create(
                    feedback=self.feedback, created_by=self.manager,
                )

    def test_default_status_and_priority(self):
        complaint = Complaint.objects.create(
            feedback=self.feedback, created_by=self.manager,
        )
        self.assertEqual(complaint.status, Complaint.Status.NEW)
        self.assertEqual(complaint.priority, Complaint.Priority.MEDIUM)
