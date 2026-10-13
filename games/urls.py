from django.urls import path

from . import views

urlpatterns = [
    path("players/", views.PlayersView.as_view(), name="games-players"),
    path("me/", views.OverviewView.as_view(), name="games-overview"),
    path("challenges/", views.ChallengeView.as_view(), name="games-challenge"),
    path("bot/", views.BotGameView.as_view(), name="games-bot"),
    path("quick-match/", views.QuickMatchView.as_view(), name="games-quick-match"),
    path("<uuid:game_id>/", views.GameDetailView.as_view(), name="games-detail"),
    path("<uuid:game_id>/accept/", views.AcceptView.as_view(), name="games-accept"),
    path("<uuid:game_id>/decline/", views.DeclineView.as_view(), name="games-decline"),
    path("<uuid:game_id>/cancel/", views.CancelView.as_view(), name="games-cancel"),
    path("<uuid:game_id>/rematch/", views.RematchView.as_view(), name="games-rematch"),
    path("<uuid:game_id>/not-now/", views.NotNowView.as_view(), name="games-not-now"),
]
