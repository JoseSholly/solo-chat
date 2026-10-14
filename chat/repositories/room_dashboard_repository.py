from dataclasses import dataclass, field

from django.db.models import Count, Exists, OuterRef, Subquery
from django.db.models.functions import Coalesce

from chat.models import Message, Room, RoomMembership


@dataclass
class DashboardData:
    rooms: list = field(default_factory=list)
    last_message_map: dict = field(default_factory=dict)
    unread_data: dict = field(default_factory=dict)  # only rooms with unread messages


class RoomDashboardRepository:
    @staticmethod
    def get_user_dashboard(user) -> DashboardData:
        """The user's rooms with member count, latest message and unread count.

        Two queries, however many rooms there are. Each query is a round trip
        to the database, so everything that can be computed per room is
        computed inside the first one:
          1. rooms, with member count, latest message id, the user's own
             `last_seen` and the number of messages after it;
          2. the latest message of each room, with its sender.
        """
        mine = RoomMembership.objects.filter(user=user, room=OuterRef("pk"))
        latest_message = (
            Message.objects.filter(room=OuterRef("pk"))
            .order_by("-timestamp")
            .values("id")[:1]
        )
        unread = (
            Message.objects.filter(
                room=OuterRef("pk"), timestamp__gt=OuterRef("my_last_seen")
            )
            .order_by()
            .values("room")
            .annotate(c=Count("pk"))
            .values("c")
        )
        rooms = list(
            Room.objects.filter(Exists(mine))
            .annotate(
                member_count_annotation=Count("memberships", distinct=True),
                latest_message_id=Subquery(latest_message),
                my_last_seen=Subquery(mine.values("last_seen")[:1]),
            )
            .annotate(unread_annotation=Coalesce(Subquery(unread), 0))
            .order_by("-created_at")
        )
        if not rooms:
            return DashboardData()

        latest_ids = [r.latest_message_id for r in rooms if r.latest_message_id]
        last_message_map = {
            m.room_id: m
            for m in (
                Message.objects.select_related("sender").filter(id__in=latest_ids)
                if latest_ids
                else []
            )
        }
        unread_data = {r.id: r.unread_annotation for r in rooms if r.unread_annotation}

        return DashboardData(
            rooms=rooms, last_message_map=last_message_map, unread_data=unread_data
        )
