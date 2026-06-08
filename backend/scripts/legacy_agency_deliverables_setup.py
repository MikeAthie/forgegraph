from __future__ import annotations

import json
from pathlib import Path

from application.services.legacy_weekend_pipeline import run_legacy_weekend_pipeline
from infrastructure.orm.models import User

EMAIL = "hermes.operator+atlas@forgegraph.local"
ROOT = Path("/app/.hermes/legacy_deliverables")


def run() -> dict[str, object]:
    user = User.objects.get(email=EMAIL)
    return run_legacy_weekend_pipeline(user=user, root=ROOT, company_name="Legacy")


print(json.dumps(run(), indent=2, sort_keys=True))
