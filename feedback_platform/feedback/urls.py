from django.urls import path

from .views import (
    BranchQRCodeListView,
    DownloadExecutivePDFReportView,
    DownloadQRCodeView,
    ManagerAnalyticsView,
    PublicFeedbackSubmitView,
    RotateQRCodeView,
)

urlpatterns = [
    path("feedback/submit/<str:token>/", PublicFeedbackSubmitView.as_view(), name="public-feedback-submit"),
    path("feedback/qr/branches/", BranchQRCodeListView.as_view(), name="branch-qr-code-list"),
    path("feedback/qr/download/<uuid:branch_id>/", DownloadQRCodeView.as_view(), name="download-qr-code"),
    path("feedback/qr/rotate/<uuid:branch_id>/", RotateQRCodeView.as_view(), name="rotate-qr-code"),
    path("analytics/overview/", ManagerAnalyticsView.as_view(), name="manager-analytics-overview"),
    path("reports/executive-pdf/", DownloadExecutivePDFReportView.as_view(), name="executive-pdf-report"),
]

