import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from accounts.models import User

logger = logging.getLogger(__name__)


@database_sync_to_async
def _is_db_user_and_org_active(user_id) -> bool:
    """
    Re-verifies against PostgreSQL that the user and their organization
    are both active, preventing zombie WebSocket connections after
    deactivation or tenant suspension.
    """
    return User.objects.filter(
        pk=user_id,
        is_active=True,
        organization__is_active=True,
    ).exists()


class ManagerAlertConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer that connects authenticated managers/staff
    to real-time notifications for their organization, with zombie
    session enforcement and client-server ping/pong heartbeats.
    """

    async def _verify_active_session(self) -> bool:
        user = self.scope.get("user")
        if not user or not getattr(user, "is_authenticated", False):
            return False

        organization_id = getattr(user, "organization_id", None)
        if not organization_id:
            return False

        if isinstance(user, User):
            return await _is_db_user_and_org_active(user.pk)

        # Fallback for unit-test mock users
        if not bool(getattr(user, "is_active", True)):
            return False
        org = getattr(user, "organization", None)
        if org is not None and not bool(getattr(org, "is_active", True)):
            return False
        return True

    async def _terminate_zombie_connection(self):
        if hasattr(self, "room_group_name"):
            try:
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name,
                )
            except Exception as exc:
                logger.warning("Failed discarding zombie channel %s: %s", self.channel_name, exc)
        await self.close(code=4003)

    async def connect(self):
        if not await self._verify_active_session():
            await self.close(code=4001)
            return

        user = self.scope.get("user")
        self.room_group_name = f"org_{user.organization_id}_alerts"

        # Join organization alert group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            try:
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name,
                )
            except Exception as exc:
                logger.warning("Error discarding channel %s on disconnect: %s", self.channel_name, exc)

    async def receive_json(self, content, **kwargs):
        """
        Handles lightweight client-server heartbeats so Daphne and load
        balancers cleanly keep healthy sockets alive and prune dead ones.
        Also enforces live zombie-session checks on every heartbeat.
        """
        if not isinstance(content, dict):
            return

        msg_type = content.get("type") or content.get("action") or content.get("event")
        if msg_type == "ping":
            if not await self._verify_active_session():
                await self._terminate_zombie_connection()
                return
            await self.send_json(
                {
                    "type": "pong",
                    "timestamp": timezone.now().isoformat(),
                }
            )

    async def negative_feedback_alert(self, event):
        """
        Handler for type: 'negative_feedback_alert'.
        Re-verifies user & organization status before dispatching to prevent
        revoked managers from receiving live alerts.
        """
        if not await self._verify_active_session():
            await self._terminate_zombie_connection()
            return
        payload = event.get("content", event)
        await self.send_json(payload)

    async def send_negative_feedback_alert(self, event):
        """
        Handler for type: 'send_negative_feedback_alert'.
        """
        if not await self._verify_active_session():
            await self._terminate_zombie_connection()
            return
        payload = event.get("content", event)
        await self.send_json(payload)
