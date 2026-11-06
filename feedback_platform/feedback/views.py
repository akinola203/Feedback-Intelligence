import io
import qrcode
from datetime import datetime, time

from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Case, Count, IntegerField, When
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

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
