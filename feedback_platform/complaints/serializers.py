from rest_framework import serializers

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
            "created_at",
            "notes",
        ]

