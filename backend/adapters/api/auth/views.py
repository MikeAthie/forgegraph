"""
Auth API views.

Clean Architecture: Interface Adapters layer.
"""

import datetime
from typing import Any, Literal, cast, Union

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated, BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken, Token
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
    # Use a type-safe getter for the lifetime setting
    jwt_settings = getattr(settings, "SIMPLE_JWT", {})
    lifetime = jwt_settings.get("REFRESH_TOKEN_LIFETIME")
    
    # Ensure it's actually a timedelta before calling total_seconds()
    max_age: int | None = None
    if isinstance(lifetime, datetime.timedelta):
        max_age = int(lifetime.total_seconds())

    samesite = cast(Literal["Lax", "Strict", "None", False], 
                    getattr(settings, "AUTH_REFRESH_COOKIE_SAMESITE", "Lax"))
    
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE,
        refresh_token,
        max_age=max_age,
        httponly=True,
        secure=getattr(settings, "AUTH_REFRESH_COOKIE_SECURE", True),
        samesite=samesite,
        path=getattr(settings, "AUTH_REFRESH_COOKIE_PATH", "/"),
        domain=getattr(settings, "AUTH_REFRESH_COOKIE_DOMAIN", None),
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE,
        path=getattr(settings, "AUTH_REFRESH_COOKIE_PATH", "/"),
        domain=getattr(settings, "AUTH_REFRESH_COOKIE_DOMAIN", None),
    )


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.create_user(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class LoginView(BaseTokenObtainPairView):
    """User login endpoint."""
    
    # To fix the tuple[()] error without an ignore, we must match the type 
    # expected by the underlying TokenViewBase stub exactly.
    # If the stub says tuple[()], it effectively forbids runtime permission overrides.
    # Instead, we define the property to return the correct type.
    @property
    def permission_classes(self) -> list[type[BasePermission]]:
        return [AllowAny]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        response = super().post(request, *args, **kwargs)
        if response.status_code != status.HTTP_200_OK:
            return response

        refresh_token = response.data.get("refresh")
        if refresh_token:
            _set_refresh_cookie(response, str(refresh_token))
            response.data.pop("refresh", None)

        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh_token_raw = serializer.validated_data.get("refresh") or request.COOKIES.get(
            settings.AUTH_REFRESH_COOKIE
        )
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)

        if not refresh_token_raw:
            return response

        try:
            # RefreshToken constructor expects a 'Token' object or None according to stubs.
            # We must use 'cast' to tell Mypy this string is being treated as the 
            # appropriate token type for the constructor's signature.
            token = RefreshToken(cast(Token, refresh_token_raw))
            token.blacklist()
        except (TokenError, AttributeError):
            return response

        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)


class TokenRefreshView(BaseTokenRefreshView):
    @property
    def permission_classes(self) -> list[type[BasePermission]]:
        return [AllowAny]

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
            _set_refresh_cookie(response, str(refresh_token))
            response.data.pop("refresh", None)

        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response