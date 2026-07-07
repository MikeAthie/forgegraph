from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from application.services.gemini_media import (  # noqa: E402
    MediaGenerationService,
    media_generation_job_payload,
    read_media_asset_version_content,
)
from infrastructure.orm.models import APIKey, Graph, User  # noqa: E402

RUN_ID = datetime.now(UTC).strftime("forgegraph_media_smoke_%Y%m%d_%H%M%S")
PROVIDER = os.environ.get("FORGEGRAPH_MEDIA_PROVIDER", "google").strip().lower()
MODEL_OVERRIDE = os.environ.get("FORGEGRAPH_MEDIA_MODEL", "").strip()
OUT_DIR = Path(".hermes") / "forgegraph_media_generation_smoke" / RUN_ID
OUT_DIR.mkdir(parents=True, exist_ok=True)

prompts = [
    "Premium product photography for a sunglasses campaign called Legacy Optical Noir. One pair of black acetate sunglasses on smoked glass and black marble, cinematic noir lighting, crisp realistic reflections, subtle copper rim light, high-end optical catalog quality, no text, no logo, no people, no hands, no watermark, square social crop.",
    "Luxury editorial still life for premium sunglasses: dark charcoal lenses on ivory travertine stone, black lacquer background plane, restrained CDMX evening mood, clean negative space, realistic commercial photography, premium optical brand feel, no text, no logo, no people, no hands, no watermark, square Instagram crop.",
    "Cinematic macro product photo of premium black acetate sunglasses, close-up hinge and lens detail, dark smoke background, aged brass accent reflection, sharp material realism, noir fashion editorial lighting, no typography, no logo, no people, no watermark, square social asset.",
    "High-end optical campaign flat lay: three distinct sunglasses silhouettes arranged on dark suede and brushed gunmetal, palette of black, smoke grey, ivory and warm brass, realistic luxury product photography, no labels, no typography, no logos, no people, no watermark, square crop.",
]

credential = APIKey.objects.filter(provider=PROVIDER).order_by("-created_at").first()
if credential is None:
    raise SystemExit(f"No ForgeGraph {PROVIDER} media credential found. Configure/import a production media provider first.")
company = (
    Graph.objects.filter(organization=credential.organization, external_ref="phase-0-company").first()
    or Graph.objects.filter(organization=credential.organization).order_by("created_at").first()
)
if company is None:
    raise SystemExit("No company graph found for the media credential organization.")
user = credential.user or User.objects.order_by("date_joined").first()
if user is None:
    raise SystemExit("No user found. Seed ForgeGraph user state first.")

service = MediaGenerationService()
manifest: dict[str, object] = {
    "run_id": RUN_ID,
    "created_at": datetime.now(UTC).isoformat(),
    "execution": "ForgeGraph MediaGenerationService.create_job, not Hermes image_generate",
    "company_id": str(company.id),
    "company_name": company.name,
    "user_id": str(user.id),
    "credential_id": str(credential.id),
    "provider": credential.provider,
    "provider_requested": PROVIDER,
    "model_override": MODEL_OVERRIDE,
    "output_dir": str(OUT_DIR),
    "jobs": [],
}

for idx, prompt in enumerate(prompts, start=1):
    job = service.create_job(
        user=user,
        company=company,
        credential=credential,
        modality="image",
        prompt=prompt,
        idempotency_key=f"{RUN_ID}:legacy-optical-noir:{idx}",
        model=MODEL_OVERRIDE,
    )
    job_info = media_generation_job_payload(job)
    if job.status == "succeeded" and job.output_asset_version_id:
        content, mime_type, filename = read_media_asset_version_content(job.output_asset_version)
        suffix = ".png" if "png" in mime_type else Path(filename).suffix or ".bin"
        saved_path = OUT_DIR / f"legacy_optical_noir_{idx:02d}{suffix}"
        saved_path.write_bytes(content)
        job_info["copied_output_path"] = str(saved_path)
        job_info["copied_output_bytes"] = len(content)
        job_info["copied_output_mime_type"] = mime_type
    manifest["jobs"].append(job_info)

manifest_path = OUT_DIR / "manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
print(json.dumps({"run_id": RUN_ID, "manifest_path": str(manifest_path), "jobs": manifest["jobs"]}, indent=2, sort_keys=True))
