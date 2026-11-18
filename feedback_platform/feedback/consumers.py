import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from accounts.models import User
from organizations.models import UserBranch

logger = logging.getLogger(__name__)


@database_sync_to_async
def _get_active_user_groups(user_id):
    """
    Re-verifies against PostgreSQL that the user and their organization are both
    active, and returns the exact list of channel groups the user is authorized
    to subscribe to:
      - Organization Admins: org-wide alert group (`org_{org_id}_alerts`).
      - Branch Managers / Staff: strictly scoped per-branch groups
        (`branch_{branch_id}_alerts`) so managers can never eavesdrop on
        unassigned branches.
    Returns None if the user or organization is inactive/revoked.
    """
    user = (
        User.objects.select_related("organization")
        .filter(pk=user_id, is_active=True, organization__is_active=True)
        .first()
    )
    if not user:
        return None

    if user.role == User.Role.ADMIN or user.is_staff or user.is_superuser:
        return [f"org_{user.organization_id}_alerts"]

    branch_ids = list(
        UserBranch.objects.filter(
            user_id=user.pk,
            branch__organization_id=user.organization_id,
            branch__is_active=True,
        ).values_list("branch_id", flat=True)
    )
    return [f"branch_{bid}_alerts" for bid in branch_ids]


@database_sync_to_async
def _is_db_user_authorized_for_branch(user_id, branch_id=None) -> bool:
    """
    Re-verifies that the user & org remain active, and (when branch_id is given
    for non-admin roles) that the user is still assigned to that branch.
    """
    user = (
        User.objects.select_related("organization")
        .filter(pk=user_id, is_active=True, organization__is_active=True)
        .first()
    )
    if not user:
        return False

    if not branch_id or user.role == User.Role.ADMIN or user.is_staff or user.is_superuser:
        return True

    return UserBranch.objects.filter(
        user_id=user.pk,
        branch_id=branch_id,
        branch__organization_id=user.organization_id,
        branch__is_active=True,
    ).exists()


class ManagerAlertConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer that connects authenticated managers/staff
    to real-time negative feedback notifications strictly scoped by
    their authorized organization/branch permissions, with zombie-session
    enforcement and client-server ping/pong heartbeats.
    """

    async def _resolve_authorized_groups(self):
        user = self.scope.get("user")
        if not user or not getattr(user, "is_authenticated", False):
            return None

        organization_id = getattr(user, "organization_id", None)
        if not organization_id:
            return None

        if isinstance(user, User):
            return await _get_active_user_groups(user.pk)

        # Fallback for unit-test mock users
        if not bool(getattr(user, "is_active", True)):
            return None
        org = getattr(user, "organization", None)
        if org is not None and not bool(getattr(org, "is_active", True)):
            return None
        return [f"org_{organization_id}_alerts"]

    async def _verify_active_session(self, branch_id=None) -> bool:
        user = self.scope.get("user")
        if not user or not getattr(user, "is_authenticated", False):
            return False

        organization_id = getattr(user, "organization_id", None)
        if not organization_id:
            return False

        if isinstance(user, User):
            return await _is_db_user_authorized_for_branch(user.pk, branch_id=branch_id)

        if not bool(getattr(user, "is_active", True)):
            return False
        org = getattr(user, "organization", None)
        if org is not None and not bool(getattr(org, "is_active", True)):
            return False
        return True

    async def _leave_all_groups(self):
        for group_name in getattr(self, "room_group_names", []):
            try:
                await self.channel_layer.group_discard(
                    group_name,
                    self.channel_name,
                )
            except Exception as exc:
                logger.warning("Failed discarding channel %s from %s: %s", self.channel_name, group_name, exc)

    async def _terminate_zombie_connection(self):
        await self._leave_all_groups()
        await self.close(code=4003)

    async def connect(self):
        groups = await self._resolve_authorized_groups()
        if groups is None:
            await self.close(code=4001)
            return

        self.room_group_names = groups
        for group_name in self.room_group_names:
            await self.channel_layer.group_add(
                group_name,
                self.channel_name,
            )
        await self.accept()

    async def disconnect(self, close_code):
        await self._leave_all_groups()

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
        Re-verifies user, organization, and branch authorization before forwarding
        so revoked or reassigned managers never receive unauthorized alerts.
        """
        payload = event.get("content", event)
        branch_id = payload.get("branch_id") if isinstance(payload, dict) else None
        if not await self._verify_active_session(branch_id=branch_id):
            await self._terminate_zombie_connection()
            return
        await self.send_json(payload)

    async def send_negative_feedback_alert(self, event):
        """
        Handler for type: 'send_negative_feedback_alert'.
        """
        payload = event.get("content", event)
        branch_id = payload.get("branch_id") if isinstance(payload, dict) else None
        if not await self._verify_active_session(branch_id=branch_id):
            await self._terminate_zombie_connection()
            return
        await self.send_json(payload)

    async def send_task_delegated_alert(self, event):
        """
        Handler for type: 'send_task_delegated_alert'.
        Re-verifies active session and branch authorization before notifying
        connected sector managers and org admins of task delegation events.
        """
        payload = event.get("content", event)
        branch_id = payload.get("branch_id") if isinstance(payload, dict) else None
        if not await self._verify_active_session(branch_id=branch_id):
            await self._terminate_zombie_connection()
            return
        await self.send_json(payload)
