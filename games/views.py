from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import game_state, user_brief
from .services import GameError, GameService, MatchmakingService, PresenceService


def _error(exc: GameError) -> Response:
    return Response(
        {"error": exc.message, "code": exc.code, **exc.extra}, status=exc.status
    )


class PlayersView(APIView):
    """Online players by default; `?q=` searches everyone by name."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = request.query_params.get("q", "").strip().lstrip("@")
        if q:
            users = list(
                get_user_model()
                .objects.filter(Q(username__icontains=q) | Q(display_name__icontains=q))
                .exclude(pk=request.user.pk)
                .order_by("username")[:20]
            )
            online_ids = set(
                get_user_model()
                .objects.filter(
                    PresenceService.online_q(), pk__in=[u.pk for u in users]
                )
                .values_list("pk", flat=True)
            )
        else:
            users = PresenceService.online_users(exclude=request.user)
            online_ids = {u.pk for u in users}

        stats = GameService.stats_for(users)
        players = [
            {
                **user_brief(u, request),
                "online": u.pk in online_ids,
                "stats": stats[u.pk],
            }
            for u in users
        ]
        # Online first, so a search shows who can actually play now.
        players.sort(key=lambda p: not p["online"])
        return Response(players)


class OverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = GameService.overview(request.user)

        def states(games):
            return [game_state(g, request) for g in games]

        return Response(
            {
                "stats": data["stats"],
                "bot_stats": data["bot_stats"],
                "incoming": states(data["incoming"]),
                "outgoing": states(data["outgoing"]),
                "active": states(data["active"]),
                "recent": states(data["recent"]),
                "queued": data["queued"],
                "online_count": len(PresenceService.online_users(exclude=request.user)),
            }
        )


class ChallengeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            game = GameService.challenge(request.user, request.data.get("username", ""))
        except GameError as exc:
            return _error(exc)
        return Response(game_state(game, request), status=status.HTTP_201_CREATED)


class GameDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, game_id):
        game = GameService.get(game_id)
        if game is None:
            return Response(
                {"error": "Game not found.", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not game.is_player(request.user):
            return Response(
                {"error": "You're not in this game.", "code": "forbidden"},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(game_state(game, request))


def _game_action(method):
    class _View(APIView):
        permission_classes = [IsAuthenticated]

        def post(self, request, game_id):
            try:
                game = method(game_id, request.user)
            except GameError as exc:
                return _error(exc)
            return Response(game_state(game, request))

    return _View


AcceptView = _game_action(GameService.accept)
DeclineView = _game_action(GameService.decline)
CancelView = _game_action(GameService.cancel)
RematchView = _game_action(GameService.rematch)


class BotGameView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            game = GameService.play_bot(
                request.user, request.data.get("level", "medium")
            )
        except GameError as exc:
            return _error(exc)
        return Response(game_state(game, request), status=status.HTTP_201_CREATED)


class QuickMatchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        game = MatchmakingService.join(request.user)
        if game is None:
            return Response(
                {
                    "status": "waiting",
                    "online_count": len(
                        PresenceService.online_users(exclude=request.user)
                    ),
                },
                status=status.HTTP_202_ACCEPTED,
            )
        return Response({"status": "matched", "game": game_state(game, request)})

    def delete(self, request):
        MatchmakingService.leave(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
