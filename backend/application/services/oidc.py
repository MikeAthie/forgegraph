from __future__ import annotations

from typing import Any, cast
from urllib.parse import quote

import requests
from django.core import signing
from django.core.cache import cache
from django.core.signing import BadSignature, SignatureExpired
from jose import jwk, jwt
from jose.utils import base64url_decode

from infrastructure.orm.models import OIDCProvider

_OIDC_CONFIG_CACHE_KEY = "oidc_config:{issuer}"
_OIDC_JWKS_CACHE_KEY = "oidc_jwks:{issuer}"


def get_oidc_config(issuer_url: str) -> dict[str, Any]:
    issuer = issuer_url.rstrip("/")
    cache_key = _OIDC_CONFIG_CACHE_KEY.format(issuer=issuer)
    cached = cache.get(cache_key)
    if cached:
        return cast(dict[str, Any], cached)

    response = requests.get(f"{issuer}/.well-known/openid-configuration", timeout=10)
    response.raise_for_status()
    config = cast(dict[str, Any], response.json())
    cache.set(cache_key, config, timeout=6 * 60 * 60)
    return config


def get_oidc_jwks(issuer_url: str) -> dict[str, Any]:
    issuer = issuer_url.rstrip("/")
    cache_key = _OIDC_JWKS_CACHE_KEY.format(issuer=issuer)
    cached = cache.get(cache_key)
    if cached:
        return cast(dict[str, Any], cached)

    config = get_oidc_config(issuer)
    jwks_uri = config.get("jwks_uri")
    if not jwks_uri:
        raise ValueError("jwks_uri missing from OIDC configuration")

    response = requests.get(jwks_uri, timeout=10)
    response.raise_for_status()
    jwks = cast(dict[str, Any], response.json())
    cache.set(cache_key, jwks, timeout=6 * 60 * 60)
    return jwks


def build_authorize_url(
    provider: OIDCProvider,
    *,
    redirect_uri: str,
    state: str,
    nonce: str,
    login_hint: str | None = None,
) -> str:
    config = get_oidc_config(provider.issuer_url)
    authorization_endpoint = config.get("authorization_endpoint")
    if not authorization_endpoint:
        raise ValueError("authorization_endpoint missing from OIDC configuration")

    params = {
        "client_id": provider.client_id,
        "response_type": "code",
        "scope": "openid profile email",
        "redirect_uri": redirect_uri,
        "state": state,
        "nonce": nonce,
    }
    if provider.audience:
        params["audience"] = provider.audience
    if login_hint:
        params["login_hint"] = login_hint

    query = "&".join(f"{key}={quote(str(value))}" for key, value in params.items())
    return f"{authorization_endpoint}?{query}"


def exchange_code_for_tokens(
    provider: OIDCProvider,
    *,
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    config = get_oidc_config(provider.issuer_url)
    token_endpoint = config.get("token_endpoint")
    if not token_endpoint:
        raise ValueError("token_endpoint missing from OIDC configuration")

    response = requests.post(
        token_endpoint,
        data={
            "grant_type": "authorization_code",
            "client_id": provider.client_id,
            "client_secret": provider.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=10,
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


def verify_id_token(
    provider: OIDCProvider,
    *,
    id_token: str,
    nonce: str,
) -> dict[str, Any]:
    config = get_oidc_config(provider.issuer_url)
    jwks = get_oidc_jwks(provider.issuer_url)

    headers = cast(dict[str, Any], jwt.get_unverified_header(id_token))
    kid = headers.get("kid")
    keys = jwks.get("keys", [])

    key = next((k for k in keys if k.get("kid") == kid), None)
    if not key:
        raise ValueError("Unable to find matching JWKS key for token")

    public_key = jwk.construct(key)
    message, encoded_sig = id_token.rsplit(".", 1)
    decoded_sig = base64url_decode(encoded_sig.encode("utf-8"))

    if not public_key.verify(message.encode("utf-8"), decoded_sig):
        raise ValueError("Invalid ID token signature")

    claims = cast(dict[str, Any], jwt.get_unverified_claims(id_token))
    if claims.get("iss") != config.get("issuer"):
        raise ValueError("Invalid issuer")

    audience = claims.get("aud")
    if isinstance(audience, list):
        if provider.client_id not in audience:
            raise ValueError("Invalid audience")
    elif audience != provider.client_id:
        raise ValueError("Invalid audience")

    if claims.get("nonce") != nonce:
        raise ValueError("Invalid nonce")

    return claims


def sign_state(payload: dict[str, Any], *, salt: str = "oidc-sso") -> str:
    return signing.dumps(payload, salt=salt)


def verify_state(state: str, *, max_age: int = 600, salt: str = "oidc-sso") -> dict[str, Any]:
    try:
        return cast(dict[str, Any], signing.loads(state, salt=salt, max_age=max_age))
    except SignatureExpired as exc:  # pragma: no cover - defensive
        raise ValueError("SSO state expired") from exc
    except BadSignature as exc:
        raise ValueError("Invalid SSO state") from exc
