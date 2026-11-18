from rest_framework import serializers

from accounts.models import User
from organizations.models import Sector, UserBranch
from .models import Complaint, ComplaintNote


class ComplaintNoteSerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source="author.email", read_only=True)
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = ComplaintNote
        fields = ["id", "author_email", "author_name", "body", "created_at"]
        read_only_fields = ["id", "author_email", "author_name", "created_at"]

    def get_author_name(self, obj):
        if obj.author_id:
            return obj.author.full_name or obj.author.email
        return "System"


class ComplaintSerializer(serializers.ModelSerializer):
    feedback_rating = serializers.IntegerField(source="feedback.rating", read_only=True)
    feedback_message = serializers.CharField(source="feedback.message", read_only=True)
    feedback_category = serializers.CharField(source="feedback.category.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    sector_label = serializers.CharField(source="get_sector_display", read_only=True)
    assigned_to_email = serializers.EmailField(source="assigned_to.email", read_only=True, allow_null=True)
    assigned_to_name = serializers.SerializerMethodField()
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True, allow_null=True)
    delegated_by_email = serializers.EmailField(source="delegated_by.email", read_only=True, allow_null=True)
    delegated_by_name = serializers.SerializerMethodField()
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
            "sector",
            "sector_label",
            "status",
            "priority",
            "assigned_to",
            "assigned_to_email",
            "assigned_to_name",
            "created_by_email",
            "delegated_by",
            "delegated_by_email",
            "delegated_by_name",
            "delegated_at",
            "due_at",
            "resolved_at",
            "resolution_summary",
            "created_at",
            "notes",
        ]
        read_only_fields = [
            "id",
            "feedback",
            "branch",
            "sector_label",
            "created_by_email",
            "delegated_by",
            "delegated_by_email",
            "delegated_by_name",
            "delegated_at",
            "resolved_at",
            "created_at",
            "notes",
        ]

    def get_assigned_to_name(self, obj):
        if obj.assigned_to_id:
            return obj.assigned_to.full_name or obj.assigned_to.email
        return None

    def get_delegated_by_name(self, obj):
        if obj.delegated_by_id:
            return obj.delegated_by.full_name or obj.delegated_by.email
        return None

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


class DelegateComplaintSerializer(serializers.Serializer):
    assigned_to_id = serializers.UUIDField()
    sector = serializers.ChoiceField(choices=Sector.choices, required=False)
    priority = serializers.CharField(required=False)
    due_at = serializers.DateTimeField(required=False, allow_null=True)
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")

    def validate_priority(self, value):
        normalized = (value or "").strip().lower()
        valid = set(Complaint.Priority.values)
        if normalized not in valid:
            raise serializers.ValidationError(
                f"Invalid priority '{value}'. Must be one of: {', '.join(sorted(valid))}."
            )
        return normalized
