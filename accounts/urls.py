from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path("signup/", views.SignupView.as_view(), name="auth-signup"),
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("me/", views.ProfileView.as_view(), name="auth-profile"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path(
        "users/<str:username>/",
        views.UserPublicProfileView.as_view(),
        name="user-public-profile",
    ),
]
