from django.urls import path

from .views import (
    ComplaintDelegateView,
    ComplaintDelegatesListView,
    ComplaintDetailView,
    ComplaintListCreateView,
    ComplaintNoteCreateView,
)

urlpatterns = [
    path("complaints/", ComplaintListCreateView.as_view(), name="complaint-list-create"),
    path("complaints/delegates/", ComplaintDelegatesListView.as_view(), name="complaint-delegates"),
    path("complaints/<uuid:id>/", ComplaintDetailView.as_view(), name="complaint-detail"),
    path("complaints/<uuid:id>/delegate/", ComplaintDelegateView.as_view(), name="complaint-delegate"),
    path("complaints/<uuid:complaint_id>/notes/", ComplaintNoteCreateView.as_view(), name="complaint-note-create"),
]
