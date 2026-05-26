from django.utils import timezone

from chat.models import Room, RoomMembership


class RoomService:
    @staticmethod
    def get_or_create(name: str) -> tuple[Room, bool]:
        return Room.objects.get_or_create(name=name)

    @staticmethod
    def get(name: str) -> Room | None:
        try:
            return Room.objects.get(name=name)
        except Room.DoesNotExist:
            return None

    @staticmethod
    def get_by_slug(slug) -> Room | None:
        try:
            return Room.objects.get(slug=slug)
        except Room.DoesNotExist:
            return None

    @staticmethod
    def create(user, name: str, description: str = "") -> Room:
        room = Room.objects.create(name=name, description=description, creator=user)
        RoomMembership.objects.create(user=user, room=room)
        return room

    @staticmethod
    def add_member(user, room: Room) -> tuple[RoomMembership, bool]:
        return RoomMembership.objects.get_or_create(user=user, room=room)

    @staticmethod
    def remove_member(user, room: Room) -> None:
        RoomMembership.objects.filter(user=user, room=room).delete()

    @staticmethod
    def is_member(user, room: Room) -> bool:
        if not user or not user.is_authenticated:
            return False
        return RoomMembership.objects.filter(user=user, room=room).exists()

    @staticmethod
    def update_last_seen(user, room: Room) -> None:
        RoomMembership.objects.filter(user=user, room=room).update(last_seen=timezone.now())
