from django.urls import re_path
from .consumers import ManagerAlertConsumer

websocket_urlpatterns = [
    re_path(r"^ws/alerts/manager/?$", ManagerAlertConsumer.as_asgi()),
]

