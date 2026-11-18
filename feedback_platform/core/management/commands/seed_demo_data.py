from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User
from complaints.models import Complaint, ComplaintNote
from feedback.models import Category, Feedback, QRCode
from organizations.models import Branch, Organization, Sector, UserBranch


class Command(BaseCommand):
    help = (
        "Idempotently seeds comprehensive demo data for FreshMart Supermarkets "
        "including organizations, branches, sector-mapped categories, QR codes, "
        "admin/branch/sector managers, historical feedback, and delegated complaints."
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

        # 3. Categories (Global + Custom, mapped to supermarket sectors)
        def _ensure_category(cat_org, name, default_sector):
            cat, _ = Category.objects.get_or_create(
                organization=cat_org,
                name=name,
                defaults={"is_active": True, "default_sector": default_sector},
            )
            if cat.default_sector != default_sector:
                cat.default_sector = default_sector
                cat.save(update_fields=["default_sector"])
            return cat

        cat_service = _ensure_category(None, "Customer Service", Sector.CUSTOMER_SERVICE)
        cat_quality = _ensure_category(None, "Product Quality", Sector.COLD_CHAIN_MEAT)
        cat_checkout = _ensure_category(None, "Pricing & Checkout", Sector.POS_CASHIER)
        cat_cleanliness = _ensure_category(None, "Cleanliness & Facilities", Sector.FACILITY_SECURITY)
        cat_bakery = _ensure_category(org, "Bakery & Deli", Sector.BAKERY_PRODUCE)
        cat_produce = _ensure_category(org, "Fresh Produce & Meat", Sector.BAKERY_PRODUCE)

        # 4. QR Codes
        qr_lekki = QRCode.objects.filter(branch=branch_lekki, is_active=True).first()
        if not qr_lekki:
            qr_lekki = QRCode.objects.create(branch=branch_lekki, is_active=True)

        qr_ikeja = QRCode.objects.filter(branch=branch_ikeja, is_active=True).first()
        if not qr_ikeja:
            qr_ikeja = QRCode.objects.create(branch=branch_ikeja, is_active=True)

        # 5. Users (Org Admin + General Branch Managers + Sector Leads)
        def _ensure_user(email, password, role, full_name, is_staff=False):
            user = User.objects.filter(organization=org, email=email).first()
            if not user:
                user = User.objects.create_user(
                    organization=org,
                    email=email,
                    password=password,
                    role=role,
                    full_name=full_name,
                    is_staff=is_staff,
                    is_superuser=False,
                )
            else:
                user.set_password(password)
                user.full_name = full_name
                user.role = role
                user.is_staff = is_staff
                user.is_active = True
                user.save()
            return user

        def _ensure_branch_link(user, branch, sector, is_sector_lead=False):
            link, _ = UserBranch.objects.get_or_create(
                user=user,
                branch=branch,
                defaults={
                    "organization": org,
                    "sector": sector,
                    "is_sector_lead": is_sector_lead,
                },
            )
            if link.sector != sector or link.is_sector_lead != is_sector_lead:
                link.sector = sector
                link.is_sector_lead = is_sector_lead
                link.save(update_fields=["sector", "is_sector_lead"])
            return link

        admin_email = "admin@freshmart.ng"
        admin_pass = "AdminPass123!"
        admin_user = _ensure_user(
            admin_email, admin_pass, User.Role.ADMIN, "Chidi Okafor (COO)", is_staff=True
        )

        manager_pass = "ManagerPass123!"
        lekki_manager_email = "lekki.manager@freshmart.ng"
        lekki_manager = _ensure_user(
            lekki_manager_email,
            manager_pass,
            User.Role.MANAGER,
            "Amina Bello (Lekki General Manager)",
        )
        _ensure_branch_link(lekki_manager, branch_lekki, Sector.GENERAL, is_sector_lead=True)

        ikeja_manager_email = "ikeja.manager@freshmart.ng"
        ikeja_manager = _ensure_user(
            ikeja_manager_email,
            manager_pass,
            User.Role.MANAGER,
            "Tunde Bakare (Ikeja General Manager)",
        )
        _ensure_branch_link(ikeja_manager, branch_ikeja, Sector.GENERAL, is_sector_lead=True)

        # Dedicated Sector Leads at Lekki Phase 1
        bakery_lead_email = "bakery.lekki@freshmart.ng"
        bakery_lead = _ensure_user(
            bakery_lead_email,
            manager_pass,
            User.Role.MANAGER,
            "Chioma Obi (Bakery & Produce Lead)",
        )
        _ensure_branch_link(bakery_lead, branch_lekki, Sector.BAKERY_PRODUCE, is_sector_lead=True)

        pos_lead_email = "pos.lekki@freshmart.ng"
        pos_lead = _ensure_user(
            pos_lead_email,
            manager_pass,
            User.Role.MANAGER,
            "Seyi Ogunleye (POS & Cashiers Lead)",
        )
        _ensure_branch_link(pos_lead, branch_lekki, Sector.POS_CASHIER, is_sector_lead=True)

        coldchain_lead_email = "coldchain.lekki@freshmart.ng"
        coldchain_lead = _ensure_user(
            coldchain_lead_email,
            manager_pass,
            User.Role.MANAGER,
            "Ibrahim Musa (Cold Chain & Dairy Lead)",
        )
        _ensure_branch_link(coldchain_lead, branch_lekki, Sector.COLD_CHAIN_MEAT, is_sector_lead=True)

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
                fb.created_at = now - timedelta(days=days_ago, hours=rating * 2)
                fb.save(update_fields=["created_at"])
            created_feedback_list.append(fb)

        # 7. Seed 5 Active Delegated Complaints with Sector Routing & Notes
        negative_feedbacks = [f for f in created_feedback_list if f.rating <= 2]

        if len(negative_feedbacks) >= 5:
            # Complaint 1: URGENT / IN_PROGRESS — Delegated to Cold Chain Lead
            c1, _ = Complaint.objects.update_or_create(
                feedback=negative_feedbacks[0],
                defaults={
                    "organization": org,
                    "branch": negative_feedbacks[0].branch,
                    "sector": Sector.COLD_CHAIN_MEAT,
                    "status": Complaint.Status.IN_PROGRESS,
                    "priority": Complaint.Priority.URGENT,
                    "assigned_to": coldchain_lead,
                    "created_by": admin_user,
                    "delegated_by": lekki_manager,
                    "delegated_at": now - timedelta(hours=6),
                    "due_at": now + timedelta(hours=6),
                },
            )
            if not c1.notes.exists():
                ComplaintNote.objects.create(
                    complaint=c1,
                    author=lekki_manager,
                    body=(
                        "[DELEGATED to Ibrahim Musa (Cold Chain & Dairy Lead) — "
                        "Cold Chain, Dairy & Butchery] Inspect dairy chiller temperature "
                        "on Aisle 4 immediately and pull affected milk batch."
                    ),
                )

            # Complaint 2: URGENT / IN_PROGRESS — Delegated to POS & Cashiers Lead
            c2, _ = Complaint.objects.update_or_create(
                feedback=negative_feedbacks[1],
                defaults={
                    "organization": org,
                    "branch": negative_feedbacks[1].branch,
                    "sector": Sector.POS_CASHIER,
                    "status": Complaint.Status.IN_PROGRESS,
                    "priority": Complaint.Priority.URGENT,
                    "assigned_to": pos_lead,
                    "created_by": admin_user,
                    "delegated_by": admin_user,
                    "delegated_at": now - timedelta(hours=12),
                    "due_at": now + timedelta(hours=12),
                },
            )
            if not c2.notes.exists():
                ComplaintNote.objects.create(
                    complaint=c2,
                    author=admin_user,
                    body=(
                        "[DELEGATED to Seyi Ogunleye (POS & Cashiers Lead) — "
                        "Front-End POS & Cashiers] Audit Counter 3 shift handover and "
                        "open an express lane during 4pm–7pm peak."
                    ),
                )
                ComplaintNote.objects.create(
                    complaint=c2,
                    author=pos_lead,
                    body="Reviewed CCTV for Counter 3. Deploying float cashier for peak shift transitions.",
                )

            # Complaint 3: HIGH / REVIEWED — Ikeja POS discrepancy
            c3, _ = Complaint.objects.update_or_create(
                feedback=negative_feedbacks[2],
                defaults={
                    "organization": org,
                    "branch": negative_feedbacks[2].branch,
                    "sector": Sector.POS_CASHIER,
                    "status": Complaint.Status.REVIEWED,
                    "priority": Complaint.Priority.HIGH,
                    "assigned_to": ikeja_manager,
                    "created_by": admin_user,
                    "delegated_by": admin_user,
                    "delegated_at": now - timedelta(days=1),
                },
            )
            if not c3.notes.exists():
                ComplaintNote.objects.create(
                    complaint=c3,
                    author=ikeja_manager,
                    body="Shelf tag discrepancy verified. Floor supervisor is auditing all price tags in aisle 4.",
                )

            # Complaint 4: HIGH / RESOLVED — Lekki Facility & Stocking
            c4, _ = Complaint.objects.update_or_create(
                feedback=negative_feedbacks[3],
                defaults={
                    "organization": org,
                    "branch": negative_feedbacks[3].branch,
                    "sector": Sector.FACILITY_SECURITY,
                    "status": Complaint.Status.RESOLVED,
                    "priority": Complaint.Priority.HIGH,
                    "assigned_to": lekki_manager,
                    "created_by": admin_user,
                    "delegated_by": admin_user,
                    "delegated_at": now - timedelta(days=4),
                    "resolved_at": now - timedelta(days=2),
                    "resolution_summary": "Night restocking protocol enforced. Daytime restock pallets prohibited between 4 PM and 9 PM.",
                },
            )
            if not c4.notes.exists():
                ComplaintNote.objects.create(
                    complaint=c4,
                    author=lekki_manager,
                    body="Warehouse staff instructed to keep all daytime stock trolleys off primary customer aisles.",
                )

            # Complaint 5: MEDIUM / CLOSED — Ikeja Bakery
            c5, _ = Complaint.objects.update_or_create(
                feedback=negative_feedbacks[4],
                defaults={
                    "organization": org,
                    "branch": negative_feedbacks[4].branch,
                    "sector": Sector.BAKERY_PRODUCE,
                    "status": Complaint.Status.CLOSED,
                    "priority": Complaint.Priority.MEDIUM,
                    "assigned_to": ikeja_manager,
                    "created_by": admin_user,
                    "delegated_by": admin_user,
                    "delegated_at": now - timedelta(days=5),
                    "resolved_at": now - timedelta(days=3),
                    "resolution_summary": "Deli supplier batch returned and bakery refrigeration temperature recalibrated.",
                },
            )

        # 8. Print Executive Summary Table
        scan_base = getattr(settings, "FRONTEND_SCAN_BASE_URL", "http://localhost:3000/scan")
        scan_lekki = f"{scan_base.rstrip('/')}/{qr_lekki.token}"
        scan_ikeja = f"{scan_base.rstrip('/')}/{qr_ikeja.token}"

        divider = "=" * 84
        subdivider = "-" * 84

        self.stdout.write(self.style.SUCCESS(f"\n{divider}"))
        self.stdout.write(self.style.SUCCESS("    FRESHMART SUPERMARKETS — SECTOR DELEGATION DEMO SEEDING COMPLETE"))
        self.stdout.write(self.style.SUCCESS(f"{divider}"))
        self.stdout.write(f"Organization: {org.name} (Slug: '{org.slug}')")
        self.stdout.write(f"Total Feedback: {Feedback.objects.filter(organization=org).count()} items")
        self.stdout.write(f"Total Complaints: {Complaint.objects.filter(organization=org).count()} active escalations")
        self.stdout.write(f"\n{subdivider}")
        self.stdout.write("PORTAL LOGIN CREDENTIALS:")
        self.stdout.write(f"  • Org Admin:          {admin_email:<28} / {admin_pass} (All Branches)")
        self.stdout.write(f"  • Lekki Gen Manager:  {lekki_manager_email:<28} / {manager_pass} (GENERAL — Lead)")
        self.stdout.write(f"  • Lekki Bakery Lead:  {bakery_lead_email:<28} / {manager_pass} (BAKERY_PRODUCE — Lead)")
        self.stdout.write(f"  • Lekki POS Lead:     {pos_lead_email:<28} / {manager_pass} (POS_CASHIER — Lead)")
        self.stdout.write(f"  • Lekki Cold Chain:   {coldchain_lead_email:<28} / {manager_pass} (COLD_CHAIN_MEAT — Lead)")
        self.stdout.write(f"  • Ikeja Gen Manager:  {ikeja_manager_email:<28} / {manager_pass} (GENERAL — Lead)")
        self.stdout.write(f"\n{subdivider}")
        self.stdout.write("BRANCHES & ACTIVE QR SCAN URLS:")
        self.stdout.write(f"  1. {branch_lekki.name} (ID: {branch_lekki.id})")
        self.stdout.write(f"     Token:    {qr_lekki.token}")
        self.stdout.write(f"     Scan URL: {scan_lekki}")
        self.stdout.write(f"  2. {branch_ikeja.name} (ID: {branch_ikeja.id})")
        self.stdout.write(f"     Token:    {qr_ikeja.token}")
        self.stdout.write(f"     Scan URL: {scan_ikeja}")
        self.stdout.write(self.style.SUCCESS(f"{divider}\n"))
