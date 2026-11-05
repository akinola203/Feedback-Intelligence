from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from audit.models import AuditLog
from organizations.models import UserBranch
from .models import Complaint, ComplaintNote
from .serializers import ComplaintNoteSerializer, ComplaintSerializer


def get_accessible_branch_ids(user: User):
    """Returns list of branch UUIDs the user is authorized to view or manage."""
    if user.role == User.Role.ADMIN:
        return list(user.organization.branches.filter(is_active=True).values_list("id", flat=True))
    return list(UserBranch.objects.filter(user=user).values_list("branch_id", flat=True))


class ComplaintListCreateView(generics.ListCreateAPIView):
    serializer_class = ComplaintSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        branch_ids = get_accessible_branch_ids(user)
        qs = Complaint.objects.select_related(
            "feedback__category", "branch", "assigned_to", "created_by"
        ).prefetch_related("notes__author").filter(
            organization=user.organization,
            branch_id__in=branch_ids,
        )

        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)

        priority_param = self.request.query_params.get("priority")
        if priority_param:
            qs = qs.filter(priority=priority_param)

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
            metadata={"status": complaint.status, "priority": complaint.priority},
        )


class ComplaintDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = ComplaintSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        user = self.request.user
        branch_ids = get_accessible_branch_ids(user)
        return Complaint.objects.select_related(
            "feedback__category", "branch", "assigned_to", "created_by"
        ).prefetch_related("notes__author").filter(
            organization=user.organization,
            branch_id__in=branch_ids,
        )

    def perform_update(self, serializer):
        user = self.request.user
        old_status = self.get_object().status
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
                "assigned_to": instance.assigned_to.email if instance.assigned_to else None,
            },
        )


class ComplaintNoteCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, complaint_id):
        user = request.user
        branch_ids = get_accessible_branch_ids(user)

        complaint = get_object_or_404(
            Complaint,
            id=complaint_id,
            organization=user.organization,
            branch_id__in=branch_ids,
        )

        body = (request.data.get("body") or "").strip()
        if not body:
            return Response({"error": "Note body is required."}, status=status.HTTP_400_BAD_REQUEST)

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
