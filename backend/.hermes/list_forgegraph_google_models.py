from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from infrastructure.crypto.encryption import decrypt_api_key  # noqa: E402
from infrastructure.orm.models import APIKey  # noqa: E402

credential = APIKey.objects.filter(provider="google").order_by("-created_at").first()
if credential is None:
    raise SystemExit("no google credential")
api_key = decrypt_api_key(bytes(credential.encrypted_key)).strip()
resp = requests.get(
    f"{settings.GEMINI_API_BASE_URL}/models",
    headers={"x-goog-api-key": api_key},
    timeout=120,
)
payload = resp.json()
models = []
for model in payload.get("models", []):
    name = str(model.get("name") or "")
    methods = model.get("supportedGenerationMethods") or []
    if any("generate" in str(method).lower() or "predict" in str(method).lower() for method in methods):
        models.append({
            "name": name,
            "displayName": model.get("displayName"),
            "methods": methods,
        })
print(json.dumps({"status_code": resp.status_code, "models": models}, indent=2, sort_keys=True))
