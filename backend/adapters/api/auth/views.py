"""
Auth API views.

Clean Architecture: Interface Adapters layer.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal, cast

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponseNotAllowed, JsonResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
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
    ForgeGraphTokenObtainPairSerializer,
    LogoutSerializer,
    RegisterSerializer,
    UserSerializer,
)
from adapters.api.authentication import RevocableJWTAuthentication
from application.services.auth_state import (
    async_cache_increment_with_ttl,
    async_issue_ws_ticket,
    async_validate_access_token,
    issue_ws_ticket,
    revoke_access_token,
)
from application.services.tenancy import ensure_default_organization, get_default_membership
from infrastructure.orm.models import User

UserModel = get_user_model()


class DynamicScopedRateThrottle(ScopedRateThrottle):
    """Scoped throttle that honors override_settings in tests and env-loaded rates in prod."""

    def get_rate(self) -> str | None:
        throttle_rates = cast(
            dict[str, str | None],
            settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {}),
        )
        self.THROTTLE_RATES = throttle_rates
        return super().get_rate()


@dataclass(frozen=True)
class WSTicketTokenUser:
    """Lightweight authenticated user for WS ticket issuance from JWT claims."""

    id: str
    default_organization_id: str
    organization_role: str
    is_authenticated: bool = True

    @property
    def pk(self) -> str:
        return self.id


class WSTicketJWTAuthentication(RevocableJWTAuthentication):
    """JWT auth optimized for single-use WebSocket ticket issuance."""

    def get_user(self, validated_token: Any) -> Any:
        user_id_claim = cast(dict[str, Any], settings.SIMPLE_JWT).get("USER_ID_CLAIM", "user_id")
        user_id = str(validated_token.get(user_id_claim) or "").strip()
        organization_id = str(validated_token.get("default_organization_id") or "").strip()
        organization_role = str(validated_token.get("organization_role") or "").strip()
        if user_id and organization_id and organization_role:
            return WSTicketTokenUser(
                id=user_id,
                default_organization_id=organization_id,
                organization_role=organization_role,
            )
        return super().get_user(validated_token)


def _ws_permissions_for_role(role: str) -> list[str]:
    permissions = {"organizations:state:view", "runs:view"}
    if role in {"member", "admin", "owner"}:
        permissions.add("runs:operate")
    if role in {"admin", "owner"}:
        permissions.add("runs:admin")
    return sorted(permissions)


def _bearer_token_from_request(request: HttpRequest) -> str:
    raw_header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not raw_header.startswith(prefix):
        return ""
    return raw_header[len(prefix) :].strip()


def _resolve_ws_claims_from_db(user_id: str) -> tuple[str, str] | None:
    user = UserModel.objects.filter(pk=user_id).first()
    if user is None:
        return None
    membership = get_default_membership(user) or ensure_default_organization(user)
    return str(membership.organization_id), membership.role


def _parse_rate(rate: str | None) -> tuple[int, int] | None:
    raw = str(rate or "").strip().lower()
    if not raw:
        return None
    try:
        count_text, period = raw.split("/", 1)
        count = int(count_text)
    except (TypeError, ValueError):
        return None
    windows = {
        "s": 1,
        "sec": 1,
        "second": 1,
        "seconds": 1,
        "m": 60,
        "min": 60,
        "minute": 60,
        "minutes": 60,
        "h": 60 * 60,
        "hour": 60 * 60,
        "hours": 60 * 60,
        "d": 60 * 60 * 24,
        "day": 60 * 60 * 24,
        "days": 60 * 60 * 24,
    }
    window = windows.get(period.strip())
    if count <= 0 or window is None:
        return None
    return count, window


async def _allow_ws_ticket_issue_async(user_id: str) -> bool:
    parsed = _parse_rate(
        cast(dict[str, str | None], settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {})).get(
            "auth_ws_ticket"
        )
    )
    if parsed is None:
        return True
    limit, window_seconds = parsed
    bucket = int(timezone.now().timestamp()) // window_seconds
    key = f"throttle:auth_ws_ticket:{user_id}:{bucket}"
    try:
        count = await async_cache_increment_with_ttl(key, window_seconds + 1)
    except Exception:
        return True
    return int(count) <= limit


async def ws_ticket_view(request: HttpRequest) -> JsonResponse | HttpResponseNotAllowed:
    """Issue a short-lived WebSocket ticket without the DRF sync-view hot path."""

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    raw_token = _bearer_token_from_request(request)
    if not raw_token:
        return JsonResponse({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    access_token = await async_validate_access_token(raw_token)
    if access_token is None:
        return JsonResponse({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    user_id_claim = cast(dict[str, Any], settings.SIMPLE_JWT).get("USER_ID_CLAIM", "user_id")
    user_id = str(access_token.get(user_id_claim) or "").strip()
    organization_id = str(access_token.get("default_organization_id") or "").strip()
    role = str(access_token.get("organization_role") or "").strip()
    if not user_id:
        return JsonResponse({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    if not organization_id or not role:
        resolved = await sync_to_async(_resolve_ws_claims_from_db, thread_sensitive=True)(user_id)
        if resolved is None:
            return JsonResponse({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
        organization_id, role = resolved

    allowed = await _allow_ws_ticket_issue_async(user_id)
    if not allowed:
        return JsonResponse(
            {"detail": "Request was throttled."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    ticket, expires_in = await async_issue_ws_ticket(
        access_token=access_token,
        user_id=user_id,
        org_id=organization_id,
        permissions=_ws_permissions_for_role(role),
    )
    return JsonResponse(
        {
            "ticket": ticket,
            "expires_in_seconds": expires_in,
            "expires_at": (timezone.now() + timedelta(seconds=expires_in)).isoformat(),
            "org_id": organization_id,
        },
        status=status.HTTP_201_CREATED,
    )


ws_ticket_view.csrf_exempt = True  # type: ignore[attr-defined]
ws_ticket_view.actions = {"post": "issue"}  # type: ignore[attr-defined]


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
    throttle_classes = [DynamicScopedRateThrottle]
    throttle_scope = "auth_register"

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = UserModel.objects.create_user(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        ensure_default_organization(user)
        user.refresh_from_db()

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class LoginView(BaseTokenObtainPairView):
    """User login endpoint (access token body + refresh token cookie)."""

    serializer_class = ForgeGraphTokenObtainPairSerializer
    permission_classes = (AllowAny,)  # type: ignore[assignment]
    throttle_classes = [DynamicScopedRateThrottle]
    throttle_scope = "auth_login"

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

        access_token = getattr(request, "auth", None)
        if access_token is not None:
            revoke_access_token(cast(Any, access_token))

        if not refresh_token:
            return response

        try:
            token = RefreshToken(cast(Any, refresh_token))
            token.blacklist()
        except TokenError:
            return response

        return response


class WSTicketView(APIView):
    """Issue a short-lived, single-use WebSocket ticket."""

    authentication_classes: list[type[BaseAuthentication]] = [WSTicketJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [DynamicScopedRateThrottle]
    throttle_scope = "auth_ws_ticket"

    def post(self, request: Request) -> Response:
        access_token = getattr(request, "auth", None)
        if access_token is None:
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
        user = request.user
        organization_id = str(getattr(user, "default_organization_id", "") or "").strip()
        role = str(getattr(user, "organization_role", "") or "").strip()
        if not organization_id or not role:
            db_user = cast(User, user)
            membership = get_default_membership(db_user) or ensure_default_organization(db_user)
            organization_id = str(membership.organization_id)
            role = membership.role
        if not str(getattr(user, "id", "") or "").strip():
            raise AuthenticationFailed("Token does not identify a user.")

        ticket, expires_in = issue_ws_ticket(
            access_token=cast(Any, access_token),
            user_id=str(user.id),
            org_id=organization_id,
            permissions=_ws_permissions_for_role(role),
        )
        return Response(
            {
                "ticket": ticket,
                "expires_in_seconds": expires_in,
                "expires_at": (timezone.now() + timedelta(seconds=expires_in)).isoformat(),
                "org_id": organization_id,
            },
            status=status.HTTP_201_CREATED,
        )


class MeView(APIView):
    """Get current user endpoint."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        ensure_default_organization(user)
        user.refresh_from_db()
        return Response(UserSerializer(user).data)


class TokenRefreshView(BaseTokenRefreshView):
    """Token refresh endpoint (access token body + refresh token cookie)."""

    permission_classes = (AllowAny,)  # type: ignore[assignment]
    throttle_classes = [DynamicScopedRateThrottle]
    throttle_scope = "auth_refresh"

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
