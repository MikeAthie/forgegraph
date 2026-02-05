from __future__ import annotations

import hashlib
import secrets


def hash_scim_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_scim_token() -> str:
    return secrets.token_urlsafe(32)
