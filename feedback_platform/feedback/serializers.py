from rest_framework import serializers

from .models import Feedback


class PublicFeedbackSubmissionSerializer(serializers.ModelSerializer):
    message = serializers.CharField(max_length=1000, required=False, allow_blank=True, allow_null=True)
    customer_name = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    customer_email = serializers.EmailField(max_length=254, required=False, allow_blank=True, allow_null=True)
    customer_phone = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Feedback
        fields = [
            "rating",
            "category",
            "message",
            "customer_name",
            "customer_email",
            "customer_phone",
        ]

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value
