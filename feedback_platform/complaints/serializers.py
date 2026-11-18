from rest_framework import serializers

from accounts.models import User
from organizations.models import UserBranch
from .models import Complaint, ComplaintNote


class ComplaintNoteSerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source="author.email", read_only=True)

    class Meta:
        model = ComplaintNote
        fields = ["id", "author_email", "body", "created_at"]
        read_only_fields = ["id", "author_email", "created_at"]


class ComplaintSerializer(serializers.ModelSerializer):
    feedback_rating = serializers.IntegerField(source="feedback.rating", read_only=True)
    feedback_message = serializers.CharField(source="feedback.message", read_only=True)
    feedback_category = serializers.CharField(source="feedback.category.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    assigned_to_email = serializers.EmailField(source="assigned_to.email", read_only=True, allow_null=True)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)
    notes = ComplaintNoteSerializer(many=True, read_only=True)

    class Meta:
        model = Complaint
        fields = [
            "id",
            "feedback",
            "feedback_rating",
            "feedback_message",
            "feedback_category",
            "branch",
            "branch_name",
            "status",
            "priority",
            "assigned_to",
            "assigned_to_email",
            "created_by_email",
            "resolved_at",
            "resolution_summary",
            "created_at",
            "notes",
        ]
        read_only_fields = [
            "id",
            "feedback",
            "branch",
            "created_by_email",
            "resolved_at",
            "created_at",
            "notes",
        ]

    def validate_assigned_to(self, value):
        if value is None:
            return value

        request = self.context.get("request")
        org_id = getattr(getattr(request, "user", None), "organization_id", None)
        if self.instance is not None:
            org_id = self.instance.organization_id

        if not value.is_active or (org_id and value.organization_id != org_id):
            raise serializers.ValidationError(
                "Assigned user must be an active member of this organization."
            )

        if self.instance is not None and value.role != User.Role.ADMIN:
            if not UserBranch.objects.filter(
                user=value, branch_id=self.instance.branch_id
            ).exists():
                raise serializers.ValidationError(
                    "Assigned user must be authorized for this branch."
                )

        return value
