"""
JWT authentication middleware for Django Channels.

The browser WebSocket API does not allow setting arbitrary headers, so the MVP
uses `?token=<access_jwt>` query parameters.
"""

from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken


@database_sync_to_async
def _get_user(user_id: str):
    user_model = get_user_model()
    try:
        return user_model.objects.get(id=user_id)
    except user_model.DoesNotExist:
        return AnonymousUser()


class JwtQueryStringAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        scope["user"] = AnonymousUser()

        query_string = (scope.get("query_string") or b"").decode()
        token = parse_qs(query_string).get("token", [None])[0]
        if not token:
            return await super().__call__(scope, receive, send)

        try:
            access_token = AccessToken(token)
        except TokenError:
            return await super().__call__(scope, receive, send)

        user_id_claim = getattr(settings, "SIMPLE_JWT", {}).get("USER_ID_CLAIM", "user_id")
        user_id = access_token.get(user_id_claim)
        if not user_id:
            return await super().__call__(scope, receive, send)

        scope["user"] = await _get_user(str(user_id))
        return await super().__call__(scope, receive, send)
