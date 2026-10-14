from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from .models import User


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["email", "username", "display_name", "password"]

    def validate_username(self, value):
        if not value.replace("_", "").isalnum():
            raise serializers.ValidationError(
                "Username may only contain letters, numbers, and underscores."
            )
        return value.lower()

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(email=data["email"], password=data["password"])
        if user is None:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("Account is disabled.")
        data["user"] = user
        return data


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetLinkSerializer(serializers.Serializer):
    """The uid + token pair from a reset link. Resolves to the user if the
    link is still good: right user, not expired, not already used."""

    uid = serializers.CharField()
    token = serializers.CharField()

    def validate(self, data):
        try:
            pk = force_str(urlsafe_base64_decode(data["uid"]))
            user = User.objects.get(pk=pk, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
        if user is None or not default_token_generator.check_token(user, data["token"]):
            raise serializers.ValidationError(
                "This reset link has expired or was already used."
            )
        data["user"] = user
        return data


class ResetPasswordSerializer(ResetLinkSerializer):
    # Same rule as signup
    password = serializers.CharField(write_only=True, min_length=8)


class UserProfileSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "display_name",
            "avatar",
            "avatar_url",
            "bio",
            "date_joined",
        ]
        read_only_fields = ["id", "email", "username", "date_joined"]
        extra_kwargs = {"avatar": {"write_only": True}}

    def get_avatar_url(self, obj):
        if not obj.avatar:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.avatar.url) if request else obj.avatar.url


class UserPublicProfileSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()
    game_stats = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "username",
            "display_name",
            "avatar_url",
            "bio",
            "date_joined",
            "game_stats",
        ]

    def get_game_stats(self, obj):
        from games.services import GameService

        return GameService.stats(obj)

    def get_avatar_url(self, obj):
        if not obj.avatar:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.avatar.url) if request else obj.avatar.url
