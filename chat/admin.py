from django.contrib import admin

from .models import Message, Room, RoomMembership


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display  = ["name", "creator", "member_count", "created_at"]
    search_fields = ["name"]
    readonly_fields = ["id", "slug", "created_at"]

    def member_count(self, obj):
        return obj.memberships.count()


@admin.register(RoomMembership)
class RoomMembershipAdmin(admin.ModelAdmin):
    list_display  = ["user", "room", "joined_at"]
    list_filter   = ["room"]
    search_fields = ["user__username", "room__name"]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display  = ["room", "username", "message_type", "timestamp"]
    list_filter   = ["room", "message_type"]
    search_fields = ["username", "content"]
    readonly_fields = ["id", "timestamp"]
