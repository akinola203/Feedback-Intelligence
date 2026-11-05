from django.urls import path

from .views import (
    DownloadQRCodeView,
    ManagerAnalyticsView,
    PublicFeedbackSubmitView,
)

urlpatterns = [
    path("feedback/submit/<str:token>/", PublicFeedbackSubmitView.as_view(), name="public-feedback-submit"),
    path("feedback/qr/download/<uuid:branch_id>/", DownloadQRCodeView.as_view(), name="download-qr-code"),
    path("analytics/overview/", ManagerAnalyticsView.as_view(), name="manager-analytics-overview"),
]

