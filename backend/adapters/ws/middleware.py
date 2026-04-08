"""Single-use WebSocket ticket authentication middleware for Django Channels."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from application.services.auth_state import consume_ws_ticket, is_access_jti_revoked

F = TypeVar("F", bound=Callable[..., Any])
database_sync_to_async_typed = cast(Callable[[F], F], database_sync_to_async)


@database_sync_to_async_typed
def _get_user(user_id: str) -> Any:
    user_model = get_user_model()
    try:
        return user_model.objects.get(id=user_id)
    except user_model.DoesNotExist:
        return AnonymousUser()


class JwtQueryStringAuthMiddleware(BaseMiddleware):  # type: ignore[misc]
    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[Any]],
        send: Callable[..., Awaitable[Any]],
    ) -> Any:
        scope["user"] = AnonymousUser()

        query_string = (scope.get("query_string") or b"").decode()
        ticket = parse_qs(query_string).get("ticket", [None])[0]
        if not ticket:
            return await super().__call__(scope, receive, send)

        ticket_payload = consume_ws_ticket(ticket)
        if not ticket_payload:
            return await super().__call__(scope, receive, send)

        access_jti = str(ticket_payload.get("access_jti") or "")
        if access_jti and is_access_jti_revoked(access_jti):
            return await super().__call__(scope, receive, send)

        user_id = ticket_payload.get("user_id")
        if not user_id:
            return await super().__call__(scope, receive, send)

        scope["ws_ticket"] = ticket_payload
        scope["organization_id"] = str(ticket_payload.get("org_id") or "")
        scope["permissions"] = list(ticket_payload.get("permissions") or [])
        scope["access_jti"] = access_jti
        scope["user"] = await _get_user(str(user_id))
        return await super().__call__(scope, receive, send)
