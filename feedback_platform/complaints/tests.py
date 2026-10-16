from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from complaints.models import Complaint, ComplaintNote
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
        self.staff = User.objects.create(
            organization=self.org, email="staff@example.com", password="x",
            role=User.Role.STAFF,
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

    def test_complaint_assignment_and_string_representation(self):
        complaint = Complaint.objects.create(
            feedback=self.feedback,
            created_by=self.manager,
            assigned_to=self.staff,
            status=Complaint.Status.IN_PROGRESS,
        )
        self.assertEqual(complaint.assigned_to, self.staff)
        self.assertEqual(str(complaint), f"Complaint({complaint.id}, in_progress)")

    def test_complaint_note_creation_and_string_representation(self):
        complaint = Complaint.objects.create(
            feedback=self.feedback, created_by=self.manager,
        )
        note = ComplaintNote.objects.create(
            complaint=complaint,
            author=self.manager,
            body="Called the customer to offer a refund.",
        )
        self.assertEqual(complaint.notes.count(), 1)
        self.assertEqual(complaint.notes.first(), note)
        self.assertEqual(str(note), f"Note on {complaint.id} by {self.manager.id}")

    def test_complaint_clean_validations(self):
        other_org = Organization.objects.create(name="Other Org", slug="other-org-comp")
        other_user = User.objects.create(
            organization=other_org, email="other@other.com", password="x",
            role=User.Role.STAFF,
        )
        complaint = Complaint(
            feedback=self.feedback,
            branch=self.branch,
            organization=self.org,
            created_by=other_user,
        )
        with self.assertRaises(ValidationError):
            complaint.clean()

    def test_complaint_note_clean_validations(self):
        other_org = Organization.objects.create(name="Other Org 2", slug="other-org-2")
        other_user = User.objects.create(
            organization=other_org, email="other2@other.com", password="x",
            role=User.Role.STAFF,
        )
        complaint = Complaint.objects.create(
            feedback=self.feedback, created_by=self.manager,
        )
        note = ComplaintNote(
            complaint=complaint,
            author=other_user,
            body="Cross-org note attempt.",
        )
        with self.assertRaises(ValidationError):
            note.clean()
