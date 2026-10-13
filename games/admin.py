from django.contrib import admin

from .models import Game, MatchQueueEntry, UserPresence


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "player_x",
        "player_o",
        "vs_bot",
        "status",
        "result",
        "created_at",
    ]
    list_filter = ["status", "vs_bot", "result"]
    search_fields = ["player_x__username", "player_o__username"]
    readonly_fields = ["id", "created_at", "updated_at", "finished_at"]


@admin.register(UserPresence)
class UserPresenceAdmin(admin.ModelAdmin):
    list_display = ["user", "connections", "last_seen"]
    search_fields = ["user__username"]


@admin.register(MatchQueueEntry)
class MatchQueueEntryAdmin(admin.ModelAdmin):
    list_display = ["user", "created_at"]
