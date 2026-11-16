from datetime import timedelta
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User
from complaints.models import Complaint, ComplaintNote
from feedback.models import Category, Feedback, QRCode
from organizations.models import Branch, Organization, UserBranch


class Command(BaseCommand):
    help = (
        "Idempotently seeds comprehensive demo data for FreshMart Supermarkets "
        "including organizations, branches, categories, QR codes, admin/managers, "
        "historical feedback, and active complaints."
    )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding FreshMart Supermarkets demo data..."))

        # 1. Organization
        org, _ = Organization.objects.get_or_create(
            slug="freshmart",
            defaults={
                "name": "FreshMart Supermarkets",
                "is_active": True,
            },
        )
        if not org.is_active:
            org.is_active = True
            org.save()

        # 2. Branches
        branch_lekki, _ = Branch.objects.get_or_create(
            organization=org,
            name="Lekki Phase 1",
            defaults={"is_active": True},
        )
        branch_ikeja, _ = Branch.objects.get_or_create(
            organization=org,
            name="Ikeja City Mall",
            defaults={"is_active": True},
        )

        # 3. Categories (Global + Custom)
        cat_service, _ = Category.objects.get_or_create(
            organization=None, name="Customer Service", defaults={"is_active": True}
        )
        cat_quality, _ = Category.objects.get_or_create(
            organization=None, name="Product Quality", defaults={"is_active": True}
        )
        cat_checkout, _ = Category.objects.get_or_create(
            organization=None, name="Pricing & Checkout", defaults={"is_active": True}
        )
        cat_cleanliness, _ = Category.objects.get_or_create(
            organization=None, name="Cleanliness & Facilities", defaults={"is_active": True}
        )
        cat_bakery, _ = Category.objects.get_or_create(
            organization=org, name="Bakery & Deli", defaults={"is_active": True}
        )
        cat_produce, _ = Category.objects.get_or_create(
            organization=org, name="Fresh Produce & Meat", defaults={"is_active": True}
        )

        # 4. QR Codes
        qr_lekki = QRCode.objects.filter(branch=branch_lekki, is_active=True).first()
        if not qr_lekki:
            qr_lekki = QRCode.objects.create(branch=branch_lekki, is_active=True)

        qr_ikeja = QRCode.objects.filter(branch=branch_ikeja, is_active=True).first()
        if not qr_ikeja:
            qr_ikeja = QRCode.objects.create(branch=branch_ikeja, is_active=True)

        # 5. Users (Admin + Managers)
        admin_email = "admin@freshmart.ng"
        admin_pass = "AdminPass123!"
        admin_user = User.objects.filter(organization=org, email=admin_email).first()
        if not admin_user:
            admin_user = User.objects.create_user(
                organization=org,
                email=admin_email,
                password=admin_pass,
                role=User.Role.ADMIN,
                full_name="Chidi Okafor (COO)",
                is_staff=True,
                is_superuser=False,
            )
        else:
            admin_user.set_password(admin_pass)
            admin_user.full_name = "Chidi Okafor (COO)"
            admin_user.is_staff = True
            admin_user.save()

        lekki_manager_email = "lekki.manager@freshmart.ng"
        manager_pass = "ManagerPass123!"
        lekki_manager = User.objects.filter(organization=org, email=lekki_manager_email).first()
        if not lekki_manager:
            lekki_manager = User.objects.create_user(
                organization=org,
                email=lekki_manager_email,
                password=manager_pass,
                role=User.Role.MANAGER,
                full_name="Amina Bello (Lekki Branch Manager)",
            )
        else:
            lekki_manager.set_password(manager_pass)
            lekki_manager.full_name = "Amina Bello (Lekki Branch Manager)"
            lekki_manager.save()
        UserBranch.objects.get_or_create(user=lekki_manager, branch=branch_lekki)

        ikeja_manager_email = "ikeja.manager@freshmart.ng"
        ikeja_manager = User.objects.filter(organization=org, email=ikeja_manager_email).first()
        if not ikeja_manager:
            ikeja_manager = User.objects.create_user(
                organization=org,
                email=ikeja_manager_email,
                password=manager_pass,
                role=User.Role.MANAGER,
                full_name="Tunde Bakare (Ikeja Branch Manager)",
            )
        else:
            ikeja_manager.set_password(manager_pass)
            ikeja_manager.full_name = "Tunde Bakare (Ikeja Branch Manager)"
            ikeja_manager.save()
        UserBranch.objects.get_or_create(user=ikeja_manager, branch=branch_ikeja)

        # 6. Seed Historical Feedback (25 items)
        feedback_dataset = [
            (branch_lekki, cat_quality, 1, "Spoiled milk found in the dairy fridge. Very disappointing.", "Funke Adeleke", 12),
            (branch_lekki, cat_checkout, 1, "Wait time at checkout counter 3 was over 25 minutes! Staff seemed distracted.", "Emeka Nwosu", 11),
            (branch_ikeja, cat_checkout, 2, "Price displayed on the shelf (N1,200) differed from what was charged at POS (N1,650).", "Blessing Eze", 10),
            (branch_lekki, cat_cleanliness, 2, "Aisles were overcrowded with restock cartons during peak evening rush.", "Babajide Sanwo", 9),
            (branch_ikeja, cat_bakery, 2, "Pre-packaged sandwich was stale and dry around the edges.", "Ifeanyi Okonkwo", 8),
            (branch_lekki, cat_bakery, 3, "Decent selection of bread, but almond croissants were sold out by 2pm.", "Kemi Adeyemi", 7),
            (branch_ikeja, cat_service, 3, "Security at the parking entrance was courteous, but baggage counter was slow.", "Femi Otedola", 7),
            (branch_lekki, cat_produce, 3, "Apples were fresh, but plantains were overripe.", "Halima Dangote", 6),
            (branch_ikeja, cat_cleanliness, 3, "Clean floor but restroom was out of liquid soap.", "Gbenga Daniel", 6),
            (branch_lekki, cat_produce, 4, "Great quality fresh bell peppers and sweet potatoes. Reasonable prices.", "Ngozi Okonjo", 5),
            (branch_lekki, cat_service, 4, "Cashier Mary was very polite and packed our bags neatly.", "Adeola Austin", 5),
            (branch_ikeja, cat_quality, 4, "Well stocked meat and poultry section with cold refrigeration.", "Segun Agbaje", 4),
            (branch_ikeja, cat_produce, 4, "Impressive fresh organic tomatoes and greens. Clean displays.", "Zainab Ahmed", 4),
            (branch_lekki, cat_checkout, 4, "Payment with bank transfer was verified quickly without network hiccups.", "Kayode Fayemi", 3),
            (branch_ikeja, cat_service, 4, "Staff helped locate imported gluten-free flour promptly.", "Simi Esiri", 3),
            (branch_lekki, cat_bakery, 5, "The freshly baked sourdough bread is world-class! Love it.", "Chimamanda Adichie", 2),
            (branch_lekki, cat_service, 5, "Remarkable customer care from supervisor John during return of an item.", "Folarin Falana", 2),
            (branch_ikeja, cat_quality, 5, "Consistently the cleanest supermarket in Ikeja. Everything is top-tier.", "Wizkid Balogun", 2),
            (branch_lekki, cat_checkout, 5, "Fast checkout, smiling cashiers, and air conditioning was wonderful.", "Genevieve Nnaji", 1),
            (branch_ikeja, cat_bakery, 5, "Their meat pies and sausage rolls are the best in Lagos!", "Don Jazzy Collins", 1),
            (branch_lekki, cat_cleanliness, 5, "Floor was spotless, shelves neat, and shopping carts all sanitised.", "Davido Adeleke", 1),
            (branch_ikeja, cat_produce, 5, "Super fresh watermelons and pineapples, beautifully pre-cut.", "Tiwa Savage", 1),
            (branch_lekki, cat_quality, 5, "Love the new gourmet cheese selection! Keep bringing good stuff.", "Burna Boy Ogulu", 0),
            (branch_ikeja, cat_service, 4, "Great store ambiance and helpful staff on the sales floor.", "Kunle Afolayan", 0),
            (branch_lekki, cat_produce, 4, "Very fresh vegetables and good parking attendant coordination.", "Omotola Jalade", 0),
        ]

        created_feedback_list = []
        now = timezone.now()

        for branch, cat, rating, msg, cust, days_ago in feedback_dataset:
            # Check if this exact feedback already exists to keep idempotent
            fb = Feedback.objects.filter(
                organization=org,
                branch=branch,
                customer_name=cust,
                rating=rating,
            ).first()
            if not fb:
                fb = Feedback(
                    organization=org,
                    branch=branch,
                    category=cat,
                    rating=rating,
                    message=msg,
                    customer_name=cust,
                    customer_email=f"{cust.lower().replace(' ', '.')}@example.com",
                    source=Feedback.Source.QR,
                )
                fb.save()
                # Adjust created_at for historical distribution
                fb.created_at = now - timedelta(days=days_ago, hours=rating * 2)
                fb.save(update_fields=["created_at"])
            created_feedback_list.append(fb)

        # 7. Seed 5 Active Complaints with Notes
        negative_feedbacks = [f for f in created_feedback_list if f.rating <= 2]

        if len(negative_feedbacks) >= 5:
            # Complaint 1: HIGH / NEW
            c1, _ = Complaint.objects.get_or_create(
                feedback=negative_feedbacks[0],
                defaults={
                    "organization": org,
                    "branch": negative_feedbacks[0].branch,
                    "status": Complaint.Status.NEW,
                    "priority": Complaint.Priority.HIGH,
                    "assigned_to": lekki_manager,
                    "created_by": admin_user,
                },
            )

            # Complaint 2: HIGH / IN_PROGRESS
            c2, _ = Complaint.objects.get_or_create(
                feedback=negative_feedbacks[1],
                defaults={
                    "organization": org,
                    "branch": negative_feedbacks[1].branch,
                    "status": Complaint.Status.IN_PROGRESS,
                    "priority": Complaint.Priority.HIGH,
                    "assigned_to": lekki_manager,
                    "created_by": admin_user,
                },
            )
            if not c2.notes.exists():
                ComplaintNote.objects.create(
                    complaint=c2,
                    author=lekki_manager,
                    body="Reviewed security footage of Counter 3 at 4:30 PM. Cashier shift change caused the queue backlog.",
                )
                ComplaintNote.objects.create(
                    complaint=c2,
                    author=admin_user,
                    body="Please deploy a float cashier during peak shift transitions to avoid repeat delays.",
                )

            # Complaint 3: MEDIUM / REVIEWED
            c3, _ = Complaint.objects.get_or_create(
                feedback=negative_feedbacks[2],
                defaults={
                    "organization": org,
                    "branch": negative_feedbacks[2].branch,
                    "status": Complaint.Status.REVIEWED,
                    "priority": Complaint.Priority.MEDIUM,
                    "assigned_to": ikeja_manager,
                    "created_by": admin_user,
                },
            )
            if not c3.notes.exists():
                ComplaintNote.objects.create(
                    complaint=c3,
                    author=ikeja_manager,
                    body="Shelf tag discrepancy verified. Floor supervisor is auditing all price tags in aisle 4.",
                )

            # Complaint 4: HIGH / RESOLVED
            c4, _ = Complaint.objects.get_or_create(
                feedback=negative_feedbacks[3],
                defaults={
                    "organization": org,
                    "branch": negative_feedbacks[3].branch,
                    "status": Complaint.Status.RESOLVED,
                    "priority": Complaint.Priority.HIGH,
                    "assigned_to": lekki_manager,
                    "created_by": admin_user,
                    "resolved_at": now - timedelta(days=2),
                    "resolution_summary": "Night restocking protocol enforced. Daytime restock pallets prohibited between 4 PM and 9 PM.",
                },
            )
            if not c4.notes.exists():
                ComplaintNote.objects.create(
                    complaint=c4,
                    author=lekki_manager,
                    body="Warehouse staff instructed to keep all daytime stock trolleys off the primary customer aisles.",
                )

            # Complaint 5: LOW / CLOSED
            c5, _ = Complaint.objects.get_or_create(
                feedback=negative_feedbacks[4],
                defaults={
                    "organization": org,
                    "branch": negative_feedbacks[4].branch,
                    "status": Complaint.Status.CLOSED,
                    "priority": Complaint.Priority.LOW,
                    "assigned_to": ikeja_manager,
                    "created_by": admin_user,
                    "resolved_at": now - timedelta(days=3),
                    "resolution_summary": "Deli supplier batch returned and bakery refrigeration temperature recalibrated.",
                },
            )

        # 8. Print Executive Summary Table
        scan_base = getattr(settings, "FRONTEND_SCAN_BASE_URL", "http://localhost:3000/scan")
        scan_lekki = f"{scan_base.rstrip('/')}/{qr_lekki.token}"
        scan_ikeja = f"{scan_base.rstrip('/')}/{qr_ikeja.token}"

        divider = "=" * 80
        subdivider = "-" * 80

        self.stdout.write(self.style.SUCCESS(f"\n{divider}"))
        self.stdout.write(self.style.SUCCESS("    FRESHMART SUPERMARKETS — DEMO SEEDING COMPLETE"))
        self.stdout.write(self.style.SUCCESS(f"{divider}"))
        self.stdout.write(f"Organization: {org.name} (Slug: '{org.slug}')")
        self.stdout.write(f"Total Feedback: {Feedback.objects.filter(organization=org).count()} items")
        self.stdout.write(f"Total Complaints: {Complaint.objects.filter(organization=org).count()} active escalations")
        self.stdout.write(f"\n{subdivider}")
        self.stdout.write("PORTAL LOGIN CREDENTIALS:")
        self.stdout.write(f"  • Org Admin:       {admin_email} / {admin_pass} (Full Org Access)")
        self.stdout.write(f"  • Lekki Manager:   {lekki_manager_email} / {manager_pass} (Lekki Branch)")
        self.stdout.write(f"  • Ikeja Manager:   {ikeja_manager_email} / {manager_pass} (Ikeja Branch)")
        self.stdout.write(f"\n{subdivider}")
        self.stdout.write("BRANCHES & ACTIVE QR SCAN URLS:")
        self.stdout.write(f"  1. {branch_lekki.name} (ID: {branch_lekki.id})")
        self.stdout.write(f"     Token:    {qr_lekki.token}")
        self.stdout.write(f"     Scan URL: {scan_lekki}")
        self.stdout.write(f"  2. {branch_ikeja.name} (ID: {branch_ikeja.id})")
        self.stdout.write(f"     Token:    {qr_ikeja.token}")
        self.stdout.write(f"     Scan URL: {scan_ikeja}")
        self.stdout.write(self.style.SUCCESS(f"{divider}\n"))
