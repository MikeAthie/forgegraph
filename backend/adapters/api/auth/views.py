"""
Auth API views.

Clean Architecture: Interface Adapters layer.
"""

from datetime import timedelta
from typing import Any, Literal, cast

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import (
    TokenObtainPairView as BaseTokenObtainPairView,
)
from rest_framework_simplejwt.views import (
    TokenRefreshView as BaseTokenRefreshView,
)

from adapters.api.auth.serializers import (
    LogoutSerializer,
    RegisterSerializer,
    UserSerializer,
)

User = get_user_model()


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    refresh_lifetime = cast(
        timedelta,
        settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"],
    )
    samesite = cast(
        Literal["Lax", "Strict", "None", False],
        settings.AUTH_REFRESH_COOKIE_SAMESITE,
    )
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE,
        refresh_token,
        max_age=int(refresh_lifetime.total_seconds()),
        httponly=True,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        samesite=samesite,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        domain=settings.AUTH_REFRESH_COOKIE_DOMAIN,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        domain=settings.AUTH_REFRESH_COOKIE_DOMAIN,
    )


class RegisterView(APIView):
    """User registration endpoint."""

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.create_user(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        user.refresh_from_db()

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class LoginView(BaseTokenObtainPairView):
    """User login endpoint (access token body + refresh token cookie)."""

    permission_classes = (AllowAny,)  # type: ignore[assignment]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        response = super().post(request, *args, **kwargs)
        if response.status_code != status.HTTP_200_OK:
            return response

        refresh_token = response.data.get("refresh")
        if refresh_token:
            _set_refresh_cookie(response, refresh_token)
            response.data.pop("refresh", None)

        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response


class LogoutView(APIView):
    """User logout endpoint."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh_token = serializer.validated_data.get("refresh") or request.COOKIES.get(
            settings.AUTH_REFRESH_COOKIE
        )
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)

        if not refresh_token:
            return response

        try:
            token = RefreshToken(cast(Any, refresh_token))
            token.blacklist()
        except TokenError:
            return response

        return response


class MeView(APIView):
    """Get current user endpoint."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)


class TokenRefreshView(BaseTokenRefreshView):
    """Token refresh endpoint (access token body + refresh token cookie)."""

    permission_classes = (AllowAny,)  # type: ignore[assignment]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        refresh_cookie = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE)
        data = {"refresh": refresh_cookie} if refresh_cookie else request.data

        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken("Invalid or expired refresh token.") from exc

        response = Response(serializer.validated_data, status=status.HTTP_200_OK)

        refresh_token = response.data.get("refresh")
        if refresh_token:
            _set_refresh_cookie(response, refresh_token)
            response.data.pop("refresh", None)

        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response
