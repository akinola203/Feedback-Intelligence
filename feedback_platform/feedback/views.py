import io
import qrcode
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Case, Count, IntegerField, When
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from accounts.models import User
from organizations.models import Branch, UserBranch
from .models import Category, Feedback, QRCode
from .serializers import PublicFeedbackSubmissionSerializer


class PublicFeedbackThrottle(AnonRateThrottle):
    scope = "public_feedback"
    rate = "10/minute"


class PublicFeedbackSubmitView(APIView):
    """
    Public anonymous customer feedback submission endpoint.
    GET: Returns verified store branch metadata and available categories.
    POST: Records customer feedback mapped directly to the branch identified by QR token.
    """

    permission_classes = [AllowAny]
    throttle_classes = [PublicFeedbackThrottle]

    def get(self, request, token):
        qr_obj = get_object_or_404(
            QRCode.objects.select_related("branch__organization"),
            token=token,
            is_active=True,
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

        feedback = serializer.save(
            branch=qr_obj.branch,
            organization=qr_obj.branch.organization,
            source=Feedback.Source.QR,
        )

        return Response(
            {
                "message": "Feedback submitted successfully.",
                "id": str(feedback.id),
                "sentiment": feedback.sentiment,
            },
            status=status.HTTP_201_CREATED,
        )


class DownloadQRCodeView(APIView):
    """
    Streams a PNG binary image of the branch's active QR code.
    Restricted to authenticated managers/staff assigned to the branch or org admins.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, branch_id):
        user = request.user
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
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        org = user.organization

        if user.role == User.Role.ADMIN:
            accessible_branch_ids = list(
                Branch.objects.filter(organization=org, is_active=True).values_list("id", flat=True)
            )
        else:
            accessible_branch_ids = list(
                UserBranch.objects.filter(user=user).values_list("branch_id", flat=True)
            )

        requested_branch_id = request.query_params.get("branch_id")
        if requested_branch_id:
            if requested_branch_id not in [str(b_id) for b_id in accessible_branch_ids]:
                raise PermissionDenied("You are not authorized to view analytics for this branch.")
            target_branch_ids = [requested_branch_id]
        else:
            target_branch_ids = accessible_branch_ids

        queryset = Feedback.objects.filter(
            organization=org,
            branch_id__in=target_branch_ids,
        )

        start_date_str = request.query_params.get("start_date") or ""
        end_date_str = request.query_params.get("end_date") or ""

        # Redis Cache Layer (60-second TTL to offload repeated queries)
        branch_ids_key = "_".join(sorted(str(b) for b in target_branch_ids))
        cache_key = f"analytics_{org.id}_{branch_ids_key}_{start_date_str}_{end_date_str}"
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)

        if start_date_str:
            start_date = parse_date(start_date_str)
            if start_date:
                queryset = queryset.filter(created_at__gte=datetime.combine(start_date, time.min))
        if end_date_str:
            end_date = parse_date(end_date_str)
            if end_date:
                queryset = queryset.filter(created_at__lte=datetime.combine(end_date, time.max))

        agg = queryset.aggregate(
            total_count=Count("id"),
            avg_rating=Avg("rating"),
            positive_count=Count(Case(When(sentiment=Feedback.Sentiment.POSITIVE, then=1), output_field=IntegerField())),
            neutral_count=Count(Case(When(sentiment=Feedback.Sentiment.NEUTRAL, then=1), output_field=IntegerField())),
            negative_count=Count(Case(When(sentiment=Feedback.Sentiment.NEGATIVE, then=1), output_field=IntegerField())),
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

        response_data = {
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

        # Cache response for 60 seconds
        cache.set(cache_key, response_data, timeout=60)

        return Response(response_data)


class DownloadExecutivePDFReportView(APIView):
    """
    Generates and downloads an executive PDF analytics summary report using ReportLab.
    Strictly scoped to the authenticated user's organization and assigned branch permissions.
    """

    permission_classes = [IsAuthenticated]

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
                queryset = queryset.filter(created_at__gte=datetime.combine(s_date, time.min))
        elif days_param:
            try:
                days = int(days_param)
                queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=days))
            except (ValueError, TypeError):
                queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=30))
        else:
            queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=30))

        if end_date_str:
            e_date = parse_date(end_date_str)
            if e_date:
                queryset = queryset.filter(created_at__lte=datetime.combine(e_date, time.max))

        # Aggregations
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
            textColor=colors.HexColor("#0f172a"),
        )
        subtitle_style = ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#475569"),
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
            textColor=colors.HexColor("#1e293b"),
        )
        body_cell_bold = ParagraphStyle(
            "BodyCellBold",
            parent=body_cell,
            fontName="Helvetica-Bold",
        )

        elements = []

        # Title & Subtitle
        org_name = user.organization.name if user.organization else "Organization"
        elements.append(Paragraph(f"<b>{org_name} — Executive Feedback Report</b>", title_style))
        elements.append(Spacer(1, 6))

        branch_label = "All Accessible Branches"
        if branch_param and len(filter_branch_ids) == 1:
            selected_branch = accessible_branches_qs.filter(id=filter_branch_ids[0]).first()
            if selected_branch:
                branch_label = selected_branch.name

        generated_at = timezone.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        period_label = f"Generated: {generated_at} | Scope: {branch_label}"
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
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8fafc"), colors.white]),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 20))

        # Recent Feedback Table
        elements.append(Paragraph("<b>Recent Feedback Submissions (Up to 25 items)</b>", styles["Heading2"]))
        elements.append(Spacer(1, 8))

        recent_items = list(queryset.select_related("branch", "category").order_by("-created_at")[:25])
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
                date_str = item.created_at.strftime("%Y-%m-%d %H:%M") if item.created_at else "-"
                branch_name = item.branch.name if item.branch else "-"
                cat_name = item.category.name if item.category else "General"
                rating_str = f"{item.rating}★"
                sent_str = item.sentiment.capitalize() if item.sentiment else "Neutral"
                msg_snip = (item.message or "No message")
                if len(msg_snip) > 80:
                    msg_snip = msg_snip[:77] + "..."
                cust = f"<b>{item.customer_name or 'Anonymous'}</b>: {msg_snip}"

                feedback_table_data.append([
                    Paragraph(date_str, body_cell),
                    Paragraph(branch_name, body_cell),
                    Paragraph(cat_name, body_cell),
                    Paragraph(rating_str, body_cell_bold),
                    Paragraph(sent_str, body_cell),
                    Paragraph(cust, body_cell),
                ])

            feedback_table = Table(
                feedback_table_data,
                colWidths=[70, 80, 80, 45, 55, 210]
            )
            feedback_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8fafc"), colors.white]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            elements.append(feedback_table)

        doc.build(elements)
        pdf_data = buffer.getvalue()
        buffer.close()

        response = HttpResponse(pdf_data, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="Executive_Feedback_Report_{timezone.now().strftime("%Y%m%d")}.pdf"'
        return response
