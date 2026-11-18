from uuid import UUID

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from audit.models import AuditLog
from feedback.models import _dispatch_negative_feedback_alert
from organizations.models import Sector, UserBranch
from .models import Complaint, ComplaintNote
from .serializers import (
    ComplaintNoteSerializer,
    ComplaintSerializer,
    DelegateComplaintSerializer,
)


def get_accessible_branch_ids(user: User):
    """Returns list of branch UUIDs the user is authorized to view or manage."""
    if not getattr(user, "organization_id", None):
        return []
    if user.role == User.Role.ADMIN or user.is_staff or user.is_superuser:
        return list(user.organization.branches.filter(is_active=True).values_list("id", flat=True))
    return list(
        UserBranch.objects.filter(
            user=user, branch__organization=user.organization, branch__is_active=True
        ).values_list("branch_id", flat=True)
    )


class ComplaintListCreateView(generics.ListCreateAPIView):
    serializer_class = ComplaintSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        branch_ids = get_accessible_branch_ids(user)
        qs = (
            Complaint.objects.select_related(
                "feedback__category", "branch", "assigned_to", "created_by", "delegated_by"
            )
            .prefetch_related("notes__author")
            .filter(
                organization=user.organization,
                branch_id__in=branch_ids,
            )
        )

        status_param = (self.request.query_params.get("status") or "").strip().lower()
        if status_param:
            if status_param == "open":
                qs = qs.filter(status__in=[Complaint.Status.NEW, Complaint.Status.REVIEWED])
            else:
                qs = qs.filter(status=status_param)

        priority_param = (self.request.query_params.get("priority") or "").strip().lower()
        if priority_param:
            qs = qs.filter(priority=priority_param)

        sector_param = (self.request.query_params.get("sector") or "").strip().upper()
        if sector_param:
            qs = qs.filter(sector=sector_param)

        assigned_to_me = (self.request.query_params.get("assigned_to_me") or "").strip().lower()
        if assigned_to_me in ("true", "1", "yes"):
            qs = qs.filter(assigned_to=user)

        branch_param = self.request.query_params.get("branch_id")
        if branch_param:
            if branch_param not in [str(b) for b in branch_ids]:
                raise PermissionDenied("You do not have permission for this branch.")
            qs = qs.filter(branch_id=branch_param)

        return qs

    def perform_create(self, serializer):
        user = self.request.user
        branch = serializer.validated_data.get("branch")
        branch_ids = get_accessible_branch_ids(user)
        if branch.id not in branch_ids:
            raise PermissionDenied("You cannot create a complaint for a branch you are not assigned to.")

        complaint = serializer.save(
            organization=user.organization,
            created_by=user,
        )

        AuditLog.objects.create(
            organization=user.organization,
            actor_user=user,
            entity_type="Complaint",
            entity_id=complaint.id,
            action="COMPLAINT_CREATED",
            metadata={"status": complaint.status, "priority": complaint.priority, "sector": complaint.sector},
        )


class ComplaintDelegatesListView(APIView):
    """
    Directory of eligible branch sector managers and staff for task delegation.
    Strictly scoped to the caller's organization and authorized branches.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not getattr(user, "organization_id", None):
            raise PermissionDenied("User does not belong to an organization.")

        accessible_branch_ids = get_accessible_branch_ids(user)
        branch_param = (request.query_params.get("branch_id") or "").strip()

        if branch_param:
            try:
                branch_uuid = UUID(branch_param)
            except (ValueError, TypeError):
                raise ValidationError({"branch_id": "Invalid branch UUID."})
            if branch_uuid not in accessible_branch_ids:
                raise PermissionDenied("You do not have permission to view delegates for this branch.")
            target_branch_ids = [branch_uuid]
        else:
            target_branch_ids = accessible_branch_ids

        links_qs = UserBranch.objects.select_related("user", "branch").filter(
            organization=user.organization,
            branch_id__in=target_branch_ids,
            branch__is_active=True,
            user__is_active=True,
        )

        sector_param = (request.query_params.get("sector") or "").strip().upper()
        if sector_param:
            links_qs = links_qs.filter(sector=sector_param)

        links = links_qs.order_by("-is_sector_lead", "branch__name", "user__full_name", "user__email")

        delegates = [
            {
                "user_id": str(link.user_id),
                "full_name": link.user.full_name or link.user.email,
                "email": link.user.email,
                "role": link.user.role,
                "branch_id": str(link.branch_id),
                "branch_name": link.branch.name,
                "sector": link.sector,
                "sector_label": link.get_sector_display(),
                "is_sector_lead": link.is_sector_lead,
            }
            for link in links
        ]

        return Response(
            {
                "delegates": delegates,
                "sectors": [
                    {"value": code, "label": label} for code, label in Sector.choices
                ],
            },
            status=status.HTTP_200_OK,
        )


class ComplaintDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = ComplaintSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        user = self.request.user
        branch_ids = get_accessible_branch_ids(user)
        return (
            Complaint.objects.select_related(
                "feedback__category", "branch", "assigned_to", "created_by", "delegated_by"
            )
            .prefetch_related("notes__author")
            .filter(
                organization=user.organization,
                branch_id__in=branch_ids,
            )
        )

    def get_object(self):
        locked = getattr(self, "_locked_complaint", None)
        if locked is not None:
            return locked
        return super().get_object()

    def update(self, request, *args, **kwargs):
        user = request.user
        branch_ids = get_accessible_branch_ids(user)
        complaint_id = self.kwargs.get(self.lookup_field)

        with transaction.atomic():
            # Acquire pessimistic row-level lock on Complaint before reading/mutating.
            # Deliberately omits nullable select_related joins so PostgreSQL does not
            # reject FOR UPDATE on the nullable side of a LEFT OUTER JOIN.
            locked_complaint = get_object_or_404(
                Complaint.objects.select_for_update(),
                id=complaint_id,
                organization=user.organization,
                branch_id__in=branch_ids,
            )
            self._locked_complaint = locked_complaint
            try:
                return super().update(request, *args, **kwargs)
            finally:
                self._locked_complaint = None

    def perform_update(self, serializer):
        user = self.request.user
        old_status = serializer.instance.status
        instance = serializer.save()

        # Handle resolution timestamp
        if instance.status in [Complaint.Status.RESOLVED, Complaint.Status.CLOSED] and not instance.resolved_at:
            instance.resolved_at = timezone.now()
            instance.save(update_fields=["resolved_at"])

        AuditLog.objects.create(
            organization=user.organization,
            actor_user=user,
            entity_type="Complaint",
            entity_id=instance.id,
            action="COMPLAINT_UPDATED",
            metadata={
                "previous_status": old_status,
                "new_status": instance.status,
                "sector": instance.sector,
                "priority": instance.priority,
                "assigned_to": instance.assigned_to.email if instance.assigned_to else None,
            },
        )


class ComplaintDelegateView(APIView):
    """
    Explicitly delegates/re-assigns a complaint to a sector manager or staff member
    within the same branch using pessimistic row-level locking, appends an audit
    note, records an immutable AuditLog entry, and dispatches a real-time
    WebSocket notification on transaction commit.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        user = request.user
        if not getattr(user, "organization_id", None):
            raise PermissionDenied("User does not belong to an organization.")

        # RBAC: Only Org ADMIN and branch MANAGER can delegate tasks
        if user.role == User.Role.STAFF and not user.is_staff and not user.is_superuser:
            raise PermissionDenied("Staff members do not have permission to delegate tasks.")

        serializer = DelegateComplaintSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        assigned_to_id = serializer.validated_data["assigned_to_id"]
        requested_sector = serializer.validated_data.get("sector")
        requested_priority = serializer.validated_data.get("priority")
        due_at = serializer.validated_data.get("due_at")
        has_due_at = "due_at" in serializer.validated_data
        directive = (serializer.validated_data.get("note") or "").strip()

        accessible_branch_ids = get_accessible_branch_ids(user)

        with transaction.atomic():
            complaint = get_object_or_404(
                Complaint.objects.select_for_update(),
                id=id,
                organization=user.organization,
                branch_id__in=accessible_branch_ids,
            )

            assignee = User.objects.filter(
                id=assigned_to_id,
                organization=user.organization,
                is_active=True,
            ).first()
            if not assignee:
                raise ValidationError(
                    {"assigned_to_id": "Assignee must be an active user within your organization."}
                )

            assignee_link = None
            if assignee.role != User.Role.ADMIN:
                assignee_link = UserBranch.objects.filter(
                    user=assignee,
                    branch_id=complaint.branch_id,
                    organization=user.organization,
                ).first()
                if not assignee_link:
                    raise ValidationError(
                        {"assigned_to_id": "Assignee is not assigned to this complaint's branch."}
                    )

            previous_assignee_email = complaint.assigned_to.email if complaint.assigned_to_id else None
            previous_status = complaint.status

            target_sector = (
                requested_sector
                or (assignee_link.sector if assignee_link else None)
                or complaint.sector
            )
            target_priority = requested_priority or complaint.priority

            now = timezone.now()
            complaint.assigned_to = assignee
            complaint.sector = target_sector
            complaint.priority = target_priority
            complaint.delegated_by = user
            complaint.delegated_at = now
            if has_due_at:
                complaint.due_at = due_at
            if complaint.status in (Complaint.Status.NEW, Complaint.Status.REVIEWED):
                complaint.status = Complaint.Status.IN_PROGRESS

            complaint.full_clean()
            complaint.save()

            assignee_display = assignee.full_name or assignee.email
            delegator_display = user.full_name or user.email
            sector_label = complaint.get_sector_display()
            branch_name = complaint.branch.name

            note_body = f"[DELEGATED to {assignee_display} — {sector_label}]"
            if directive:
                note_body = f"{note_body} {directive}"

            ComplaintNote.objects.create(
                complaint=complaint,
                author=user,
                body=note_body,
            )

            AuditLog.objects.create(
                organization=user.organization,
                actor_user=user,
                entity_type="Complaint",
                entity_id=complaint.id,
                action="complaint.delegated",
                metadata={
                    "previous_status": previous_status,
                    "new_status": complaint.status,
                    "previous_assignee": previous_assignee_email,
                    "assigned_to_id": str(assignee.id),
                    "assigned_to_email": assignee.email,
                    "sector": complaint.sector,
                    "priority": complaint.priority,
                    "due_at": complaint.due_at.isoformat() if complaint.due_at else None,
                },
            )

            # Schedule real-time WebSocket delegation notification strictly on DB commit
            target_groups = [
                f"org_{user.organization_id}_alerts",
                f"branch_{complaint.branch_id}_alerts",
            ]
            ws_payload = {
                "type": "send_task_delegated_alert",
                "content": {
                    "event_type": "TASK_DELEGATED",
                    "complaint_id": str(complaint.id),
                    "branch_id": str(complaint.branch_id),
                    "branch_name": branch_name,
                    "sector": complaint.sector,
                    "sector_label": sector_label,
                    "priority": complaint.priority,
                    "assigned_to_id": str(assignee.id),
                    "assigned_to_name": assignee_display,
                    "delegated_by_name": delegator_display,
                    "note": directive,
                    "created_at": now.isoformat(),
                },
            }

            def _emit_delegation_alert(groups=target_groups, data=ws_payload):
                for grp in groups:
                    _dispatch_negative_feedback_alert(grp, data)

            transaction.on_commit(_emit_delegation_alert)

        refreshed = (
            Complaint.objects.select_related(
                "feedback__category", "branch", "assigned_to", "created_by", "delegated_by"
            )
            .prefetch_related("notes__author")
            .get(pk=complaint.pk)
        )
        return Response(
            ComplaintSerializer(refreshed, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class ComplaintNoteCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, complaint_id):
        user = request.user
        branch_ids = get_accessible_branch_ids(user)

        body = (request.data.get("body") or "").strip()
        if not body:
            return Response({"error": "Note body is required."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            complaint = get_object_or_404(
                Complaint.objects.select_for_update(),
                id=complaint_id,
                organization=user.organization,
                branch_id__in=branch_ids,
            )

            note = ComplaintNote.objects.create(
                complaint=complaint,
                author=user,
                body=body,
            )

            AuditLog.objects.create(
                organization=user.organization,
                actor_user=user,
                entity_type="ComplaintNote",
                entity_id=note.id,
                action="COMPLAINT_NOTE_ADDED",
                metadata={"complaint_id": str(complaint.id)},
            )

        return Response(ComplaintNoteSerializer(note).data, status=status.HTTP_201_CREATED)
