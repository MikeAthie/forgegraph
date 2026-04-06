"""
Custom API authentication with access-token revocation checks.
"""

from __future__ import annotations

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import Token

from application.services.auth_state import is_access_token_revoked


class RevocableJWTAuthentication(JWTAuthentication):
    def get_validated_token(self, raw_token: bytes) -> Token:
        token = super().get_validated_token(raw_token)
        if is_access_token_revoked(token):
            raise AuthenticationFailed("Token has been revoked.")
        return token
