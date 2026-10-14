import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .serializers import (
    ForgotPasswordSerializer,
    LoginSerializer,
    ResetLinkSerializer,
    ResetPasswordSerializer,
    SignupSerializer,
    UserProfileSerializer,
    UserPublicProfileSerializer,
)

logger = logging.getLogger(__name__)


def _token_response(user, request=None):
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": UserProfileSerializer(user, context={"request": request}).data,
    }


class SignupView(APIView):
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )
        user = serializer.save()
        return Response(_token_response(user, request), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(_token_response(serializer.validated_data["user"], request))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": "Refresh token required.", "code": "missing_token"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(refresh_token).blacklist()
        except TokenError:
            return Response(
                {"error": "Invalid or expired token.", "code": "invalid_token"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, JSONParser]

    def get(self, request):
        return Response(
            UserProfileSerializer(request.user, context={"request": request}).data
        )

    def patch(self, request):
        serializer = UserProfileSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(
                {"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )
        serializer.save()
        return Response(serializer.data)


class UserPublicProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, username):
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return Response(
                {"error": "User not found."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(
            UserPublicProfileSerializer(user, context={"request": request}).data
        )


# ---------------------------------------------------------------------------
# Forgot / reset password — a one-hour link sent by email
# ---------------------------------------------------------------------------

FORGOT_PASSWORD_REPLY = (
    "If an account exists for that email, a reset link is on its way. "
    "It works for one hour."
)


def _send_reset_email(user, request) -> None:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    base = settings.SITE_URL or request.build_absolute_uri("/").rstrip("/")
    context = {
        "user": user,
        "reset_url": f"{base}/reset-password/{uid}/{token}/",
        "minutes": settings.PASSWORD_RESET_TIMEOUT // 60,
    }
    message = EmailMultiAlternatives(
        subject="Reset your Solo-Chat password",
        body=render_to_string("accounts/email/password_reset.txt", context),
        to=[user.email],
    )
    message.attach_alternative(
        render_to_string("accounts/email/password_reset.html", context), "text/html"
    )
    message.send(fail_silently=True)


class ForgotPasswordView(APIView):
    """Always answers the same way, so it can't reveal who has an account."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Enter a valid email address.", "code": "invalid_email"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        email = serializer.validated_data["email"]
        for user in User.objects.filter(email__iexact=email, is_active=True):
            _send_reset_email(user, request)
        return Response({"detail": FORGOT_PASSWORD_REPLY})


class ResetPasswordView(APIView):
    """GET checks a link before showing the form; POST sets the new password,
    signs out every other session and signs this browser in."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        serializer = ResetLinkSerializer(data=request.query_params)
        return Response({"valid": serializer.is_valid()})

    def post(self, request):
        # The link first: a bad link makes the password beside the point.
        link = ResetLinkSerializer(data=request.data)
        if not link.is_valid():
            return Response(
                {
                    "error": "This reset link has expired or was already used.",
                    "code": "invalid_link",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = ResetPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            message = serializer.errors.get("password", ["Choose a new password."])[0]
            return Response(
                {"error": str(message), "code": "invalid_password"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password"])  # also makes the link unusable

        for outstanding in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=outstanding)

        return Response(_token_response(user, request))
