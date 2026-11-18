import hashlib
import io
import time as time_mod
from datetime import datetime, time, timedelta, timezone as dt_timezone
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

import qrcode
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Avg, Case, Count, IntegerField, Prefetch, When
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from accounts.models import User
from organizations.models import Branch, UserBranch
from .cache import (
    ANALYTICS_CACHE_TTL,
    ANALYTICS_LOCK_TTL,
    ANALYTICS_STALE_TTL,
    build_analytics_cache_key,
)
from .models import Category, Feedback, QRCode
from .serializers import PublicFeedbackSubmissionSerializer

FEEDBACK_DEDUP_TTL_SECONDS = 30
MAX_PDF_EXPORT_ROWS = 25


def _get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


class PublicFeedbackThrottle(AnonRateThrottle):
    scope = "public_feedback"
    rate = "10/minute"


class PublicFeedbackTokenThrottle(SimpleRateThrottle):
    """Per-QR-token rate limiter to defend a single store stand against distributed floods."""
    scope = "public_feedback_token"

    def get_cache_key(self, request, view):
        token = view.kwargs.get("token")
        if not token:
            return None
        return self.cache_format % {"scope": self.scope, "ident": token}


class PDFExportThrottle(UserRateThrottle):
    scope = "pdf_export"


class PublicFeedbackSubmitView(APIView):
    """
    Public anonymous customer feedback submission endpoint.
    GET: Returns verified store branch metadata and available categories.
    POST: Records customer feedback atomically with idempotency deduplication
          to prevent mobile double-taps from creating duplicate rows or alerts.
    """

    permission_classes = [AllowAny]
    throttle_classes = [PublicFeedbackThrottle, PublicFeedbackTokenThrottle]

    def get(self, request, token):
        qr_obj = get_object_or_404(
            QRCode.objects.select_related("branch__organization"),
            token=token,
            is_active=True,
            branch__is_active=True,
            branch__organization__is_active=True,
        )
        categories = Category.objects.filter(
            organization__in=[None, qr_obj.branch.organization_id],
            is_active=True,
        ).values("id", "name")

        return Response(
            {
                "organization_name": qr_obj.branch.organization.name,
                "organization_slug": qr_obj.branch.organization.slug,
                "branch_name": qr_obj.branch.name,
                "branch_id": str(qr_obj.branch.id),
                "categories": list(categories),
            }
        )

    def post(self, request, token):
        qr_obj = get_object_or_404(
            QRCode.objects.select_related("branch__organization"),
            token=token,
            is_active=True,
            branch__is_active=True,
            branch__organization__is_active=True,
        )

        serializer = PublicFeedbackSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        category = serializer.validated_data["category"]
        if (
            category.organization_id
            and category.organization_id != qr_obj.branch.organization_id
        ):
            return Response(
                {"error": "Category is invalid for this store branch."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Short-window idempotency deduplication (supports explicit Idempotency-Key
        # or content fingerprint over [ip, branch_id, rating, comment_hash]).
        explicit_idem_key = (request.headers.get("Idempotency-Key") or "").strip()
        if explicit_idem_key:
            fingerprint = hashlib.sha256(
                f"{qr_obj.branch_id}:{explicit_idem_key}".encode("utf-8")
            ).hexdigest()
        else:
            client_ip = _get_client_ip(request)
            rating_val = serializer.validated_data["rating"]
            normalized_msg = (serializer.validated_data.get("message") or "").strip().lower()
            comment_hash = hashlib.sha256(normalized_msg.encode("utf-8")).hexdigest()
            fingerprint = hashlib.sha256(
                f"{client_ip}:{qr_obj.branch_id}:{rating_val}:{comment_hash}".encode("utf-8")
            ).hexdigest()

        dedup_lock_key = f"fb_dedup_lock:{fingerprint}"
        dedup_resp_key = f"fb_dedup_resp:{fingerprint}"

        if not cache.add(dedup_lock_key, "1", timeout=FEEDBACK_DEDUP_TTL_SECONDS):
            cached_resp = cache.get(dedup_resp_key)
            if cached_resp is not None:
                resp = Response(cached_resp, status=status.HTTP_201_CREATED)
                resp["X-Idempotent-Replay"] = "true"
                return resp
            resp = Response(
                {
                    "message": "Feedback already received and is being processed.",
                    "duplicate": True,
                },
                status=status.HTTP_201_CREATED,
            )
            resp["X-Idempotent-Replay"] = "true"
            return resp

        try:
            with transaction.atomic():
                feedback = serializer.save(
                    branch=qr_obj.branch,
                    organization=qr_obj.branch.organization,
                    source=Feedback.Source.QR,
                )

                routed_complaint = None
                if feedback.rating <= 2:
                    from complaints.models import Complaint
                    from organizations.models import Sector

                    target_sector = category.default_sector or Sector.GENERAL
                    auto_priority = (
                        Complaint.Priority.URGENT
                        if feedback.rating == 1
                        else Complaint.Priority.HIGH
                    )
                    sector_link = (
                        UserBranch.objects.select_related("user")
                        .filter(
                            branch=qr_obj.branch,
                            organization=qr_obj.branch.organization,
                            sector=target_sector,
                            user__is_active=True,
                        )
                        .order_by("-is_sector_lead", "created_at")
                        .first()
                    )
                    assignee = sector_link.user if sector_link else None

                    routed_complaint, _ = Complaint.objects.get_or_create(
                        feedback=feedback,
                        defaults={
                            "organization": qr_obj.branch.organization,
                            "branch": qr_obj.branch,
                            "sector": target_sector,
                            "priority": auto_priority,
                            "status": Complaint.Status.NEW,
                            "assigned_to": assignee,
                            "created_by": None,
                        },
                    )
        except Exception:
            cache.delete(dedup_lock_key)
            raise

        response_payload = {
            "message": "Feedback submitted successfully.",
            "id": str(feedback.id),
            "sentiment": feedback.sentiment,
        }
        if routed_complaint is not None:
            response_payload["complaint_id"] = str(routed_complaint.id)
            response_payload["routed_sector"] = routed_complaint.sector
            response_payload["priority"] = routed_complaint.priority
            response_payload["assigned_to_id"] = (
                str(routed_complaint.assigned_to_id)
                if routed_complaint.assigned_to_id
                else None
            )
        cache.set(dedup_resp_key, response_payload, timeout=FEEDBACK_DEDUP_TTL_SECONDS)

        return Response(response_payload, status=status.HTTP_201_CREATED)


class BranchQRCodeListView(APIView):
    """
    Lists all accessible branches for the authenticated user alongside each
    branch's active QR token, creation timestamp, and customer scan URL.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not getattr(user, "organization_id", None):
            raise PermissionDenied("User does not belong to an organization.")

        org = user.organization
        is_admin = user.role == User.Role.ADMIN or user.is_staff or user.is_superuser

        branches_qs = Branch.objects.filter(organization=org, is_active=True)
        if not is_admin:
            assigned_ids = UserBranch.objects.filter(
                user=user, branch__organization=org, branch__is_active=True
            ).values_list("branch_id", flat=True)
            branches_qs = branches_qs.filter(id__in=assigned_ids)

        branches = branches_qs.prefetch_related(
            Prefetch(
                "qr_codes",
                queryset=QRCode.objects.filter(is_active=True).order_by("-created_at"),
                to_attr="active_qr_list",
            )
        ).order_by("name")

        frontend_base_url = getattr(settings, "FRONTEND_SCAN_BASE_URL", "http://localhost:3000/scan")
        results = []
        for branch in branches:
            active_qr = branch.active_qr_list[0] if branch.active_qr_list else None
            results.append(
                {
                    "branch_id": str(branch.id),
                    "branch_name": branch.name,
                    "is_active": branch.is_active,
                    "qr_id": str(active_qr.id) if active_qr else None,
                    "token": active_qr.token if active_qr else None,
                    "scan_url": (
                        f"{frontend_base_url.rstrip('/')}/{active_qr.token}"
                        if active_qr
                        else None
                    ),
                    "created_at": active_qr.created_at.isoformat() if active_qr else None,
                }
            )

        return Response({"branches": results}, status=status.HTTP_200_OK)


class DownloadQRCodeView(APIView):
    """
    Streams a PNG binary image of the branch's active QR code.
    Restricted to authenticated managers/staff assigned to the branch or org admins.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, branch_id):
        user = request.user
        if not getattr(user, "organization_id", None):
            raise PermissionDenied("User does not belong to an organization.")
        org = user.organization

        branch = get_object_or_404(Branch, id=branch_id, organization=org, is_active=True)

        # RBAC Check: Organization Admin has org-wide access; Manager/Staff require explicit branch link
        if user.role != User.Role.ADMIN:
            if not UserBranch.objects.filter(user=user, branch=branch).exists():
                raise PermissionDenied("You do not have permission to download QR codes for this branch.")

        qr_obj = QRCode.objects.filter(branch=branch, is_active=True).first()
        if not qr_obj:
            raise NotFound("No active QR code currently exists for this branch.")

        frontend_base_url = getattr(settings, "FRONTEND_SCAN_BASE_URL", "http://localhost:3000/scan")
        scan_url = f"{frontend_base_url.rstrip('/')}/{qr_obj.token}"

        qr_img = qrcode.make(scan_url)
        buffer = io.BytesIO()
        qr_img.save(buffer, format="PNG")
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type="image/png")
        response["Content-Disposition"] = f'attachment; filename="qr_{branch.name}.png"'
        return response


class RotateQRCodeView(APIView):
    """
    Revokes the current active QR code for a branch and generates a fresh token.
    Restricted to authenticated managers/staff assigned to the branch or org admins.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, branch_id):
        user = request.user
        org = user.organization
        if not org:
            raise PermissionDenied("User does not belong to an organization.")

        branch = get_object_or_404(Branch, id=branch_id, organization=org, is_active=True)

        if user.role != User.Role.ADMIN and not user.is_staff and not user.is_superuser:
            if not UserBranch.objects.filter(user=user, branch=branch).exists():
                raise PermissionDenied("You do not have permission to rotate QR codes for this branch.")

        new_qr = QRCode.rotate_for_branch(branch)
        frontend_base_url = getattr(settings, "FRONTEND_SCAN_BASE_URL", "http://localhost:3000/scan")
        scan_url = f"{frontend_base_url.rstrip('/')}/{new_qr.token}"

        return Response(
            {
                "message": "QR code rotated successfully.",
                "id": str(new_qr.id),
                "token": new_qr.token,
                "scan_url": scan_url,
                "branch_id": str(branch.id),
                "branch_name": branch.name,
                "created_at": new_qr.created_at.isoformat(),
                "is_active": new_qr.is_active,
            },
            status=status.HTTP_200_OK,
        )


class ManagerAnalyticsView(APIView):
    """
    Aggregates feedback metrics, sentiment distributions, and rating statistics
    filtered by the authenticated user's organization and assigned branch(es).

    Protected against cache stampedes via:
    1. Version-bumped cache keys (invalidated on Feedback transaction commit).
    2. Single-flight distributed Redis lock (`cache.add(lock_key, "1", timeout=5)`).
    3. Stale-while-revalidate fallback during concurrent cache refreshes.
    """

    permission_classes = [IsAuthenticated]

    def _compute_analytics_payload(
        self, org, accessible_branch_ids, target_branch_ids, start_date_str, end_date_str
    ):
        queryset = Feedback.objects.filter(
            organization=org,
            branch_id__in=target_branch_ids,
        )

        if start_date_str:
            start_date = parse_date(start_date_str)
            if start_date:
                queryset = queryset.filter(
                    created_at__gte=datetime.combine(start_date, time.min, tzinfo=dt_timezone.utc)
                )
        if end_date_str:
            end_date = parse_date(end_date_str)
            if end_date:
                queryset = queryset.filter(
                    created_at__lte=datetime.combine(end_date, time.max, tzinfo=dt_timezone.utc)
                )

        agg = queryset.aggregate(
            total_count=Count("id"),
            avg_rating=Avg("rating"),
            positive_count=Count(
                Case(When(sentiment=Feedback.Sentiment.POSITIVE, then=1), output_field=IntegerField())
            ),
            neutral_count=Count(
                Case(When(sentiment=Feedback.Sentiment.NEUTRAL, then=1), output_field=IntegerField())
            ),
            negative_count=Count(
                Case(When(sentiment=Feedback.Sentiment.NEGATIVE, then=1), output_field=IntegerField())
            ),
            star_1=Count(Case(When(rating=1, then=1), output_field=IntegerField())),
            star_2=Count(Case(When(rating=2, then=1), output_field=IntegerField())),
            star_3=Count(Case(When(rating=3, then=1), output_field=IntegerField())),
            star_4=Count(Case(When(rating=4, then=1), output_field=IntegerField())),
            star_5=Count(Case(When(rating=5, then=1), output_field=IntegerField())),
        )

        total = agg["total_count"] or 0
        avg_rating = round(float(agg["avg_rating"] or 0.0), 2)

        def calc_pct(count: int) -> float:
            return round((count / total) * 100, 1) if total > 0 else 0.0

        branches = (
            Branch.objects.filter(id__in=accessible_branch_ids, is_active=True)
            .values("id", "name")
            .order_by("name")
        )

        return {
            "summary": {
                "total_feedback": total,
                "average_rating": avg_rating,
            },
            "sentiment": {
                "positive": {"count": agg["positive_count"], "percentage": calc_pct(agg["positive_count"])},
                "neutral": {"count": agg["neutral_count"], "percentage": calc_pct(agg["neutral_count"])},
                "negative": {"count": agg["negative_count"], "percentage": calc_pct(agg["negative_count"])},
            },
            "rating_distribution": {
                "5_star": {"count": agg["star_5"], "percentage": calc_pct(agg["star_5"])},
                "4_star": {"count": agg["star_4"], "percentage": calc_pct(agg["star_4"])},
                "3_star": {"count": agg["star_3"], "percentage": calc_pct(agg["star_3"])},
                "2_star": {"count": agg["star_2"], "percentage": calc_pct(agg["star_2"])},
                "1_star": {"count": agg["star_1"], "percentage": calc_pct(agg["star_1"])},
            },
            "branches": list(branches),
        }

    def get(self, request):
        user = request.user
        if not getattr(user, "organization_id", None):
            raise PermissionDenied("You must belong to an organization to view analytics.")
        org = user.organization

        if user.role == User.Role.ADMIN:
            accessible_branch_ids = list(
                Branch.objects.filter(organization=org, is_active=True).values_list("id", flat=True)
            )
        else:
            accessible_branch_ids = list(
                UserBranch.objects.filter(
                    user=user, branch__organization=org, branch__is_active=True
                ).values_list("branch_id", flat=True)
            )

        requested_branch_id = request.query_params.get("branch_id")
        if requested_branch_id:
            if requested_branch_id not in [str(b_id) for b_id in accessible_branch_ids]:
                raise PermissionDenied("You are not authorized to view analytics for this branch.")
            target_branch_ids = [requested_branch_id]
        else:
            target_branch_ids = accessible_branch_ids

        start_date_str = request.query_params.get("start_date") or ""
        end_date_str = request.query_params.get("end_date") or ""

        # Stampede-proof versioned cache keys
        cache_key = build_analytics_cache_key(
            org.id, target_branch_ids, start_date_str, end_date_str
        )
        stale_key = f"{cache_key}:stale"
        lock_key = f"{cache_key}:lock"

        # 1. Fast path: fresh cache hit
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)

        # 2. Single-flight lock acquisition (cache.add is atomic SET NX in Redis)
        lock_acquired = cache.add(lock_key, "1", timeout=ANALYTICS_LOCK_TTL)

        if not lock_acquired:
            # Stale-while-revalidate: serve recent stale snapshot immediately while leader refreshes
            stale_data = cache.get(stale_key)
            if stale_data is not None:
                return Response(stale_data)

            # Cold-start contention: briefly wait for leader to populate cache
            for _ in range(5):
                time_mod.sleep(0.05)
                cached_data = cache.get(cache_key)
                if cached_data is not None:
                    return Response(cached_data)

            # Fallback if leader failed or timed out without populating
            response_data = self._compute_analytics_payload(
                org, accessible_branch_ids, target_branch_ids, start_date_str, end_date_str
            )
            cache.set(cache_key, response_data, timeout=ANALYTICS_CACHE_TTL)
            cache.set(stale_key, response_data, timeout=ANALYTICS_STALE_TTL)
            return Response(response_data)

        try:
            # Double-check after acquiring lock in case leader just finished
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return Response(cached_data)

            response_data = self._compute_analytics_payload(
                org, accessible_branch_ids, target_branch_ids, start_date_str, end_date_str
            )
            cache.set(cache_key, response_data, timeout=ANALYTICS_CACHE_TTL)
            cache.set(stale_key, response_data, timeout=ANALYTICS_STALE_TTL)
            return Response(response_data)
        finally:
            cache.delete(lock_key)


class DownloadExecutivePDFReportView(APIView):
    """
    Generates and downloads an executive PDF analytics summary report using ReportLab.
    Strictly scoped to the authenticated user's organization and assigned branch permissions.

    Hardened against:
    - ReportLab Paragraph XML/SSRF injection via strict `xml.sax.saxutils.escape`.
    - Export DoS / RAM exhaustion via per-user concurrency locks, throttling, and row caps.
    - Timezone skew via UTC DB queries and `Africa/Lagos` display formatting.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [PDFExportThrottle]

    def get(self, request):
        user = request.user
        if not getattr(user, "organization_id", None):
            raise PermissionDenied("You must belong to an organization to export reports.")

        is_admin = user.role == User.Role.ADMIN
        if is_admin:
            accessible_branches_qs = Branch.objects.filter(
                organization=user.organization, is_active=True
            )
        else:
            accessible_branches_qs = Branch.objects.filter(
                id__in=UserBranch.objects.filter(
                    user=user, branch__organization=user.organization
                ).values_list("branch_id", flat=True),
                is_active=True,
            )

        accessible_branch_ids = set(accessible_branches_qs.values_list("id", flat=True))

        branch_param = request.query_params.get("branch_id")
        if branch_param:
            try:
                from uuid import UUID
                branch_uuid = UUID(branch_param)
            except (ValueError, TypeError):
                raise ValidationError({"branch_id": "Invalid branch UUID."})

            if branch_uuid not in accessible_branch_ids:
                raise PermissionDenied("You do not have permission to view feedback for this branch.")
            filter_branch_ids = [branch_uuid]
        else:
            filter_branch_ids = list(accessible_branch_ids)

        # Restrict concurrent PDF export requests per user to prevent RAM exhaustion
        export_lock_key = f"pdf_export_lock:{user.id}"
        if not cache.add(export_lock_key, "1", timeout=15):
            return Response(
                {"error": "A PDF export is already in progress. Please wait a moment."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            queryset = Feedback.objects.filter(
                organization=user.organization,
                branch_id__in=filter_branch_ids,
            )

            days_param = request.query_params.get("days")
            start_date_str = request.query_params.get("start_date")
            end_date_str = request.query_params.get("end_date")

            if start_date_str:
                s_date = parse_date(start_date_str)
                if s_date:
                    queryset = queryset.filter(
                        created_at__gte=datetime.combine(s_date, time.min, tzinfo=dt_timezone.utc)
                    )
            elif days_param:
                try:
                    days = max(1, min(int(days_param), 365))
                except (ValueError, TypeError):
                    days = 30
                queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=days))
            else:
                queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=30))

            if end_date_str:
                e_date = parse_date(end_date_str)
                if e_date:
                    queryset = queryset.filter(
                        created_at__lte=datetime.combine(e_date, time.max, tzinfo=dt_timezone.utc)
                    )

            # Aggregations (strictly parameterized Django ORM expressions)
            agg = queryset.aggregate(
                total_count=Count("id"),
                avg_rating=Avg("rating"),
                pos_count=Count(Case(When(sentiment=Feedback.Sentiment.POSITIVE, then=1), output_field=IntegerField())),
                neu_count=Count(Case(When(sentiment=Feedback.Sentiment.NEUTRAL, then=1), output_field=IntegerField())),
                neg_count=Count(Case(When(sentiment=Feedback.Sentiment.NEGATIVE, then=1), output_field=IntegerField())),
            )
            total = agg["total_count"] or 0
            avg_rating_val = round(float(agg["avg_rating"] or 0.0), 2)
            pos = agg["pos_count"] or 0
            neu = agg["neu_count"] or 0
            neg = agg["neg_count"] or 0

            display_tz_name = getattr(settings, "DISPLAY_TIME_ZONE", "Africa/Lagos")
            try:
                display_tz = ZoneInfo(display_tz_name)
            except Exception:
                display_tz = dt_timezone.utc
                display_tz_name = "UTC"

            # Build PDF with ReportLab
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                leftMargin=36,
                rightMargin=36,
                topMargin=36,
                bottomMargin=36,
            )

            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                "DocTitle",
                parent=styles["Heading1"],
                fontSize=18,
                leading=22,
                textColor=colors.HexColor("#000000"),
            )
            subtitle_style = ParagraphStyle(
                "DocSubtitle",
                parent=styles["Normal"],
                fontSize=10,
                leading=14,
                textColor=colors.HexColor("#525252"),
            )
            header_cell = ParagraphStyle(
                "HeaderCell",
                parent=styles["Normal"],
                fontSize=9,
                leading=11,
                fontName="Helvetica-Bold",
                textColor=colors.white,
            )
            body_cell = ParagraphStyle(
                "BodyCell",
                parent=styles["Normal"],
                fontSize=8,
                leading=11,
                textColor=colors.HexColor("#171717"),
            )
            body_cell_bold = ParagraphStyle(
                "BodyCellBold",
                parent=body_cell,
                fontName="Helvetica-Bold",
            )

            elements = []

            # Title & Subtitle (strictly XML-escaped)
            raw_org_name = user.organization.name if user.organization else "Organization"
            safe_org_name = xml_escape(str(raw_org_name))
            elements.append(Paragraph(f"<b>{safe_org_name} — Executive Feedback Report</b>", title_style))
            elements.append(Spacer(1, 6))

            branch_label = "All Accessible Branches"
            if branch_param and len(filter_branch_ids) == 1:
                selected_branch = accessible_branches_qs.filter(id=filter_branch_ids[0]).first()
                if selected_branch:
                    branch_label = selected_branch.name
            safe_branch_label = xml_escape(str(branch_label))

            now_local = timezone.now().astimezone(display_tz)
            generated_at = now_local.strftime(f"%Y-%m-%d %H:%M:%S {display_tz_name}")
            period_label = f"Generated: {xml_escape(generated_at)} | Scope: {safe_branch_label}"
            elements.append(Paragraph(period_label, subtitle_style))
            elements.append(Spacer(1, 16))

            # KPI Summary Table
            summary_data = [
                [
                    Paragraph("Metric", header_cell),
                    Paragraph("Value", header_cell),
                    Paragraph("Metric", header_cell),
                    Paragraph("Value", header_cell),
                ],
                [
                    Paragraph("Total Submissions", body_cell_bold),
                    Paragraph(str(total), body_cell),
                    Paragraph("Average Rating", body_cell_bold),
                    Paragraph(f"{avg_rating_val} / 5.0", body_cell),
                ],
                [
                    Paragraph("Positive Feedback", body_cell_bold),
                    Paragraph(f"{pos} ({(pos / total * 100):.1f}%)" if total else "0 (0.0%)", body_cell),
                    Paragraph("Negative Feedback", body_cell_bold),
                    Paragraph(f"{neg} ({(neg / total * 100):.1f}%)" if total else "0 (0.0%)", body_cell),
                ],
            ]
            summary_table = Table(summary_data, colWidths=[130, 140, 130, 140])
            summary_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#000000")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d4d4d4")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f5f5f5"), colors.white]),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            elements.append(summary_table)
            elements.append(Spacer(1, 20))

            # Recent Feedback Table (capped strictly to MAX_PDF_EXPORT_ROWS)
            elements.append(
                Paragraph(
                    f"<b>Recent Feedback Submissions (Up to {MAX_PDF_EXPORT_ROWS} items)</b>",
                    styles["Heading2"],
                )
            )
            elements.append(Spacer(1, 8))

            recent_items = list(
                queryset.select_related("branch", "category").order_by("-created_at")[:MAX_PDF_EXPORT_ROWS]
            )
            if not recent_items:
                elements.append(Paragraph("No feedback submissions recorded for this period.", subtitle_style))
            else:
                feedback_table_data = [
                    [
                        Paragraph("Date", header_cell),
                        Paragraph("Branch", header_cell),
                        Paragraph("Category", header_cell),
                        Paragraph("Rating", header_cell),
                        Paragraph("Sentiment", header_cell),
                        Paragraph("Customer & Comment", header_cell),
                    ]
                ]
                for item in recent_items:
                    date_str = (
                        item.created_at.astimezone(display_tz).strftime("%Y-%m-%d %H:%M")
                        if item.created_at
                        else "-"
                    )
                    safe_branch = xml_escape(str(item.branch.name if item.branch else "-"))
                    safe_cat = xml_escape(str(item.category.name if item.category else "General"))
                    rating_str = f"{item.rating}★"
                    sent_str = xml_escape(str(item.sentiment.capitalize() if item.sentiment else "Neutral"))
                    msg_snip = item.message or "No message"
                    if len(msg_snip) > 80:
                        msg_snip = msg_snip[:77] + "..."
                    safe_msg = xml_escape(str(msg_snip))
                    safe_cust = xml_escape(str(item.customer_name or "Anonymous"))
                    cust = f"<b>{safe_cust}</b>: {safe_msg}"

                    feedback_table_data.append([
                        Paragraph(xml_escape(date_str), body_cell),
                        Paragraph(safe_branch, body_cell),
                        Paragraph(safe_cat, body_cell),
                        Paragraph(rating_str, body_cell_bold),
                        Paragraph(sent_str, body_cell),
                        Paragraph(cust, body_cell),
                    ])

                feedback_table = Table(
                    feedback_table_data,
                    colWidths=[70, 80, 80, 45, 55, 210]
                )
                feedback_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#171717")),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e5e5")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fafafa"), colors.white]),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                elements.append(feedback_table)

            doc.build(elements)
            pdf_data = buffer.getvalue()
            buffer.close()

            response = HttpResponse(pdf_data, content_type="application/pdf")
            response["Content-Disposition"] = (
                f'attachment; filename="Executive_Feedback_Report_{now_local.strftime("%Y%m%d")}.pdf"'
            )
            response["X-Content-Type-Options"] = "nosniff"
            return response
        finally:
            cache.delete(export_lock_key)
