from dataclasses import dataclass, field

from django.db.models import Count, OuterRef, Subquery

from chat.models import Message, Room, RoomMembership


@dataclass
class DashboardData:
    rooms: list = field(default_factory=list)
    membership_map: dict = field(default_factory=dict)
    last_message_map: dict = field(default_factory=dict)
    unread_data: dict = field(default_factory=dict)


class RoomDashboardRepository:
    @staticmethod
    def get_user_dashboard(user) -> DashboardData:
        memberships = list(RoomMembership.objects.filter(user=user))
        if not memberships:
            return DashboardData()

        membership_map = {m.room_id: m for m in memberships}
        room_ids = list(membership_map.keys())

        latest_msg_sq = Subquery(
            Message.objects.filter(room_id=OuterRef("pk"))
            .order_by("-timestamp")
            .values("id")[:1]
        )
        rooms = list(
            Room.objects.filter(id__in=room_ids)
            .annotate(
                member_count_annotation=Count("memberships", distinct=True),
                latest_message_id=latest_msg_sq,
            )
            .order_by("-created_at")
        )

        latest_ids = [r.latest_message_id for r in rooms if r.latest_message_id]
        last_message_map = {
            m.room_id: m
            for m in (
                Message.objects.select_related("sender").filter(id__in=latest_ids)
                if latest_ids
                else []
            )
        }

        unread_data = dict(
            Message.objects.filter(
                room_id__in=room_ids,
                timestamp__gt=Subquery(
                    RoomMembership.objects.filter(
                        user_id=user.id, room_id=OuterRef("room_id")
                    ).values("last_seen")[:1]
                ),
            )
            .values("room_id")
            .annotate(cnt=Count("id"))
            .values_list("room_id", "cnt")
        )

        return DashboardData(
            rooms=rooms,
            membership_map=membership_map,
            last_message_map=last_message_map,
            unread_data=unread_data,
        )
