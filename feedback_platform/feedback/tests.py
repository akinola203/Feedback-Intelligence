from django.db import IntegrityError, transaction
from django.test import TestCase

from feedback.models import Category, Feedback, QRCode
from organizations.models import Branch, Organization


class CategoryUniquenessTests(TestCase):
    """
    Directly exercises correction #2: a plain composite unique constraint
    on (organization, name) would NOT stop two global (organization=NULL)
    categories with the same name, because Postgres/SQL treat NULL <> NULL.
    The partial unique indexes on the model must catch this.
    """

    def test_duplicate_global_category_name_rejected(self):
        Category.objects.create(organization=None, name="Checkout")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Category.objects.create(organization=None, name="Checkout")

    def test_seed_command_is_idempotent_and_produces_no_duplicates(self):
        from django.core.management import call_command

        call_command("seed_categories")
        call_command("seed_categories")
        self.assertEqual(
            Category.objects.filter(organization=None, name="Checkout").count(), 1
        )

    def test_org_specific_category_uniqueness_ready_but_unused_in_mvp(self):
        # The schema supports this (correction #1: extensible, not built),
        # but no MVP code path creates org-specific categories yet — this
        # test just confirms the constraint itself is sound if/when that
        # feature is turned on.
        org = Organization.objects.create(name="Org E", slug="org-e")
        Category.objects.create(organization=org, name="Custom Category")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Category.objects.create(organization=org, name="Custom Category")


class QRCodeTests(TestCase):
    def setUp(self):
        org = Organization.objects.create(name="Org F", slug="org-f")
        self.branch = Branch.objects.create(organization=org, name="Yaba")

    def test_token_is_random_and_unique(self):
        qr1 = QRCode.objects.create(branch=self.branch)
        # Deactivate before creating a second, since only one active QR
        # per branch is allowed (see next test).
        qr1.is_active = False
        qr1.save()
        qr2 = QRCode.objects.create(branch=self.branch)
        self.assertNotEqual(qr1.token, qr2.token)
        self.assertGreater(len(qr1.token), 30)

    def test_only_one_active_qr_per_branch(self):
        QRCode.objects.create(branch=self.branch)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                QRCode.objects.create(branch=self.branch)


class FeedbackSentimentTests(TestCase):
    def setUp(self):
        org = Organization.objects.create(name="Org G", slug="org-g")
        self.branch = Branch.objects.create(organization=org, name="Surulere")
        self.category = Category.objects.create(organization=None, name="Staff")

    def test_sentiment_derived_from_rating(self):
        cases = [(1, "negative"), (2, "negative"), (3, "neutral"),
                 (4, "positive"), (5, "positive")]
        for rating, expected in cases:
            fb = Feedback.objects.create(
                branch=self.branch, category=self.category, rating=rating,
            )
            self.assertEqual(fb.sentiment, expected)

    def test_organization_auto_derived_from_branch(self):
        fb = Feedback.objects.create(
            branch=self.branch, category=self.category, rating=5,
        )
        self.assertEqual(fb.organization_id, self.branch.organization_id)

    def test_rating_out_of_range_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Feedback.objects.create(
                    branch=self.branch, category=self.category, rating=6,
                )
