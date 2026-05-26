from django.urls import path

from . import views

urlpatterns = [
    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),

    # ------------------------------------------------------------------
    # Authenticated slug-based endpoints
    # UUID patterns MUST come before <str:room_name> — str matches UUIDs too
    # ------------------------------------------------------------------
    path("rooms/",                         views.RoomCreateView.as_view(),              name="room-create"),
    path("rooms/<uuid:slug>/",             views.RoomDetailView.as_view(),              name="room-detail-slug"),
    path("rooms/<uuid:slug>/upload/",      views.AuthenticatedMediaUploadView.as_view(), name="room-upload"),
    path("rooms/<uuid:slug>/delete/",      views.RoomDeleteView.as_view(),              name="room-delete"),
    path("rooms/<uuid:slug>/leave/",       views.RoomLeaveView.as_view(),               name="room-leave"),
    path("rooms/<uuid:slug>/seen/",        views.MarkRoomSeenView.as_view(),            name="room-seen"),
    path("rooms/<uuid:slug>/members/",    views.RoomMembersView.as_view(),             name="room-members"),

    # ------------------------------------------------------------------
    # Invite / join flow
    # ------------------------------------------------------------------
    path("invite/<uuid:slug>/",            views.InviteResolveView.as_view(), name="invite-resolve"),
    path("invite/<uuid:slug>/join/",       views.JoinRoomView.as_view(),      name="invite-join"),

    # ------------------------------------------------------------------
    # Legacy endpoints (old anonymous template — keep last so UUID routes win)
    # ------------------------------------------------------------------
    path("rooms/<str:room_name>/",          views.RoomGetOrCreateView.as_view(), name="room-detail"),
    path("rooms/<str:room_name>/messages/", views.MessageHistoryView.as_view(),  name="message-history"),
    path("rooms/<str:room_name>/upload/",   views.MediaUploadView.as_view(),     name="media-upload"),
    path("chat/<str:room_name>/",           views.chat_room_view,                name="chat-room"),
]
