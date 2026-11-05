from django.urls import path

from .views import (
    ComplaintDetailView,
    ComplaintListCreateView,
    ComplaintNoteCreateView,
)

urlpatterns = [
    path("complaints/", ComplaintListCreateView.as_view(), name="complaint-list-create"),
    path("complaints/<uuid:id>/", ComplaintDetailView.as_view(), name="complaint-detail"),
    path("complaints/<uuid:complaint_id>/notes/", ComplaintNoteCreateView.as_view(), name="complaint-note-create"),
]

