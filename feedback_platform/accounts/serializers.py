from rest_framework import serializers
from organizations.models import Branch, UserBranch
from .models import User


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    organization_slug = serializers.CharField()


class BranchBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "name", "is_active"]


class UserProfileSerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(source="organization.id", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    organization_slug = serializers.CharField(source="organization.slug", read_only=True)
    branches = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "role",
            "is_staff",
            "is_superuser",
            "organization_id",
            "organization_name",
            "organization_slug",
            "branches",
        ]

    def get_branches(self, user):
        if not user.organization_id:
            return []

        if user.role == User.Role.ADMIN or user.is_staff or user.is_superuser:
            branches = Branch.objects.filter(
                organization=user.organization, is_active=True
            ).order_by("name")
        else:
            branch_ids = UserBranch.objects.filter(
                user=user, branch__organization=user.organization
            ).values_list("branch_id", flat=True)
            branches = Branch.objects.filter(
                id__in=branch_ids, is_active=True
            ).order_by("name")

        return BranchBriefSerializer(branches, many=True).data
