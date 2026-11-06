import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class ManagerAlertConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer that connects authenticated managers/staff
    to real-time notifications for their organization.
    """

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close()
            return

        organization_id = getattr(user, "organization_id", None)
        if not organization_id:
            await self.close()
            return

        self.room_group_name = f"org_{organization_id}_alerts"

        # Join organization alert group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

    async def receive_json(self, content, **kwargs):
        # Client messages can be handled or acknowledged here if needed
        pass

    async def negative_feedback_alert(self, event):
        """
        Handler for type: 'negative_feedback_alert'
        """
        payload = event.get("content", event)
        await self.send_json(payload)

    async def send_negative_feedback_alert(self, event):
        """
        Handler for type: 'send_negative_feedback_alert'
        """
        payload = event.get("content", event)
        await self.send_json(payload)

