from rest_framework import serializers

from .models import Message, Room


class RoomSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    is_creator   = serializers.SerializerMethodField()

    class Meta:
        model  = Room
        fields = ["id", "name", "description", "slug", "member_count", "is_creator", "created_at"]

    def get_member_count(self, obj):
        return obj.memberships.count()

    def get_is_creator(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.creator_id == request.user.id
        return False


class MessageSerializer(serializers.ModelSerializer):
    file_url     = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    sender_id    = serializers.SerializerMethodField()
    avatar_url   = serializers.SerializerMethodField()

    class Meta:
        model  = Message
        fields = [
            "id", "room", "username", "display_name", "sender_id", "avatar_url",
            "message_type", "content", "file", "file_url", "timestamp",
        ]
        read_only_fields = ["id", "timestamp", "file_url", "display_name", "sender_id", "avatar_url"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file_url

    def get_display_name(self, obj):
        return obj.sender.display_name if obj.sender else obj.username

    def get_sender_id(self, obj):
        return str(obj.sender_id) if obj.sender_id else None

    def get_avatar_url(self, obj):
        if obj.sender and obj.sender.avatar:
            request = self.context.get("request")
            return request.build_absolute_uri(obj.sender.avatar.url) if request else obj.sender.avatar.url
        return None


class DashboardRoomSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    is_creator   = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model  = Room
        fields = [
            "id", "name", "description", "slug",
            "member_count", "is_creator",
            "last_message", "unread_count",
            "created_at",
        ]

    def get_member_count(self, obj):
        count = getattr(obj, "member_count_annotation", None)
        return count if count is not None else obj.memberships.count()

    def get_is_creator(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.creator_id == request.user.id
        return False

    def get_last_message(self, obj):
        last = self.context.get("last_message_map", {}).get(obj.id)
        if last is None:
            return None
        return {
            "display_name": last.sender.display_name if last.sender else last.username,
            "message_type": last.message_type,
            "content":      last.content if last.message_type == "text" else None,
            "timestamp":    last.timestamp.isoformat(),
        }

    def get_unread_count(self, obj):
        unread_data = self.context.get("unread_data")
        if unread_data is not None:
            return unread_data.get(obj.id, 0)
        membership_map = self.context.get("membership_map", {})
        membership = membership_map.get(obj.id)
        if membership is None:
            return 0
        return obj.messages.filter(timestamp__gt=membership.last_seen).count()
