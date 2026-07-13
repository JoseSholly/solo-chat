from dataclasses import dataclass


@dataclass(frozen=True)
class MessageCreated:
    message_id: str
    room_id: str
    room_slug: str
    room_name: str
    sender_id: str | None
    sender_username: str
    sender_display_name: str
    sender_avatar_url: str | None
    message_type: str
    content: str | None
    file_url: str | None
    timestamp: str  # ISO-8601


@dataclass(frozen=True)
class RoomCreated:
    room_id: str
    creator_id: str
    name: str


@dataclass(frozen=True)
class UserJoinedRoom:
    room_id: str
    user_id: str
    username: str
    display_name: str


@dataclass(frozen=True)
class UserLeftRoom:
    room_id: str
    user_id: str
    username: str
    display_name: str


@dataclass(frozen=True)
class LastSeenUpdated:
    room_id: str
    user_id: str
    timestamp: str  # ISO-8601
