from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from chat.models import Message, RoomMembership


@receiver(post_save, sender=Message)
def advance_sender_last_seen(sender, instance, created, **kwargs):
    if not created or instance.sender_id is None:
        return
    RoomMembership.objects.filter(
        user_id=instance.sender_id,
        room_id=instance.room_id,
    ).update(last_seen=timezone.now())
