from django.core.exceptions import ValidationError
from django.shortcuts import render

from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Room, RoomMembership
from .serializers import DashboardRoomSerializer, MessageSerializer, RoomSerializer
from .services import MediaService, MessageService, RoomService


# ---------------------------------------------------------------------------
# Legacy endpoints — kept for the old anonymous template at /chat/<room_name>/
# ---------------------------------------------------------------------------

class RoomGetOrCreateView(APIView):
    def get(self, request, room_name):
        room, _ = RoomService.get_or_create(room_name)
        return Response(RoomSerializer(room, context={"request": request}).data)


class MessageHistoryView(APIView):
    def get(self, request, room_name):
        room = RoomService.get(room_name)
        if room is None:
            return Response([], status=status.HTTP_200_OK)
        messages = MessageService.get_history(room)
        return Response(MessageSerializer(messages, many=True, context={"request": request}).data)


class MediaUploadView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request, room_name):
        room = RoomService.get(room_name)
        if room is None:
            return Response({"error": "Room not found.", "code": "not_found"}, status=status.HTTP_404_NOT_FOUND)

        file         = request.FILES.get("file")
        username     = request.data.get("username", "Anonymous")
        message_type = request.data.get("message_type", "image")

        if not file:
            return Response({"error": "No file provided.", "code": "missing_file"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            MediaService.validate(file, message_type)
        except ValidationError as exc:
            return Response({"error": exc.message, "code": "invalid_file"}, status=status.HTTP_400_BAD_REQUEST)

        sender = request.user if request.user.is_authenticated else None
        message = MessageService.create_media(room, username, message_type, file, sender=sender)
        return Response(MessageSerializer(message, context={"request": request}).data, status=status.HTTP_201_CREATED)


def chat_room_view(request, room_name):
    RoomService.get_or_create(room_name)
    return render(request, "chat/room.html", {"room_name": room_name})


# ---------------------------------------------------------------------------
# Authenticated room management endpoints
# ---------------------------------------------------------------------------

class RoomCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        name        = request.data.get("name", "").strip()
        description = request.data.get("description", "").strip()

        if not name:
            return Response(
                {"error": "Room name is required.", "code": "missing_name"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(name) > 100:
            return Response(
                {"error": "Room name must be 100 characters or fewer.", "code": "name_too_long"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if Room.objects.filter(name=name).exists():
            return Response(
                {"error": "A room with this name already exists.", "code": "name_taken"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        room = RoomService.create(request.user, name, description)
        return Response(RoomSerializer(room, context={"request": request}).data, status=status.HTTP_201_CREATED)


class RoomDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, slug):
        room = RoomService.get_by_slug(slug)
        if room is None:
            return Response({"error": "Room not found.", "code": "not_found"}, status=status.HTTP_404_NOT_FOUND)
        if room.creator_id != request.user.id:
            return Response(
                {"error": "Only the room creator can delete this room.", "code": "forbidden"},
                status=status.HTTP_403_FORBIDDEN,
            )
        room.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoomLeaveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, slug):
        room = RoomService.get_by_slug(slug)
        if room is None:
            return Response({"error": "Room not found.", "code": "not_found"}, status=status.HTTP_404_NOT_FOUND)
        if not RoomService.is_member(request.user, room):
            return Response(
                {"error": "You are not a member of this room.", "code": "not_member"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if room.creator_id == request.user.id:
            return Response(
                {"error": "Room creator cannot leave. Delete the room instead.", "code": "creator_cannot_leave"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        RoomService.remove_member(request.user, room)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Invite / join flow
# ---------------------------------------------------------------------------

class InviteResolveView(APIView):
    def get(self, request, slug):
        room = RoomService.get_by_slug(slug)
        if room is None:
            return Response(
                {"error": "Invite link is invalid or expired.", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        data = {
            "id":           str(room.id),
            "name":         room.name,
            "description":  room.description,
            "member_count": room.memberships.count(),
            "slug":         str(room.slug),
        }
        if request.user.is_authenticated:
            data["is_member"] = RoomService.is_member(request.user, room)
        return Response(data)


class JoinRoomView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, slug):
        room = RoomService.get_by_slug(slug)
        if room is None:
            return Response(
                {"error": "Invite link is invalid or expired.", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        _, created = RoomService.add_member(request.user, room)
        return Response(
            {"slug": str(room.slug), "joined": created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Dashboard and room detail
# ---------------------------------------------------------------------------

class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        memberships = (
            RoomMembership.objects
            .filter(user=request.user)
            .select_related("room")
            .order_by("-room__created_at")
        )
        rooms = [m.room for m in memberships]
        membership_map = {m.room_id: m for m in memberships}
        serializer = DashboardRoomSerializer(
            rooms,
            many=True,
            context={"request": request, "membership_map": membership_map},
        )
        return Response(serializer.data)


class RoomDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        room = RoomService.get_by_slug(slug)
        if room is None:
            return Response(
                {"error": "Room not found.", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not RoomService.is_member(request.user, room):
            return Response(
                {"error": "You are not a member of this room.", "code": "not_member"},
                status=status.HTTP_403_FORBIDDEN,
            )
        RoomService.update_last_seen(request.user, room)
        messages = MessageService.get_history(room)
        return Response({
            "room":     RoomSerializer(room, context={"request": request}).data,
            "messages": MessageSerializer(messages, many=True, context={"request": request}).data,
        })


class RoomMembersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        room = RoomService.get_by_slug(slug)
        if room is None:
            return Response({"error": "Room not found."}, status=status.HTTP_404_NOT_FOUND)
        if not RoomService.is_member(request.user, room):
            return Response({"error": "Not a member."}, status=status.HTTP_403_FORBIDDEN)

        limit  = min(int(request.query_params.get("limit", 20)), 50)
        offset = int(request.query_params.get("offset", 0))

        qs = (
            RoomMembership.objects
            .filter(room=room)
            .select_related("user")
            .order_by("user__display_name", "user__username")
        )
        total = qs.count()
        batch = qs[offset : offset + limit]

        members = []
        for m in batch:
            u = m.user
            members.append({
                "username":     u.username,
                "display_name": u.display_name or u.username,
                "avatar_url":   request.build_absolute_uri(u.avatar.url) if u.avatar else None,
            })

        return Response({"members": members, "total": total, "has_more": offset + limit < total})


class MarkRoomSeenView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, slug):
        room = RoomService.get_by_slug(slug)
        if room is None:
            return Response({"error": "Room not found.", "code": "not_found"}, status=status.HTTP_404_NOT_FOUND)
        if not RoomService.is_member(request.user, room):
            return Response({"error": "You are not a member of this room.", "code": "not_member"}, status=status.HTTP_403_FORBIDDEN)
        RoomService.update_last_seen(request.user, room)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AuthenticatedMediaUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request, slug):
        room = RoomService.get_by_slug(slug)
        if room is None:
            return Response(
                {"error": "Room not found.", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not RoomService.is_member(request.user, room):
            return Response(
                {"error": "You are not a member of this room.", "code": "not_member"},
                status=status.HTTP_403_FORBIDDEN,
            )

        file         = request.FILES.get("file")
        message_type = request.data.get("message_type", "voice")

        if not file:
            return Response(
                {"error": "No file provided.", "code": "missing_file"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            MediaService.validate(file, message_type)
        except ValidationError as exc:
            return Response(
                {"error": exc.message, "code": "invalid_file"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        message = MessageService.create_media(
            room, request.user.username, message_type, file, sender=request.user
        )
        return Response(
            MessageSerializer(message, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )
