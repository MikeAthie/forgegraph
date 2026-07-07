from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from infrastructure.orm.models import Asset, AssetVersion, PublicationDraft

SCRIPT = Path(r'C:\Users\mathi\AppData\Local\hermes\scripts\legacy_optical_noir_autopublish.py')
spec = importlib.util.spec_from_file_location('legacy_autopublish', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)  # type: ignore[union-attr]

schedule = json.loads(Path('.hermes/legacy_optical_noir_autopublish/schedule.json').read_text(encoding='utf-8'))
published_post = schedule['posts'][0]
asset_path = Path(published_post['asset_path'])
asset_hash = mod.file_sha256(asset_path)
company = PublicationDraft.objects.get(idempotency_key='legacy-optical-noir-20260629-day-3-replacement-authorized').company
organization = company.organization
asset = Asset.objects.create(
    organization=organization,
    company=company,
    title='Guardrail temporary approved asset',
    asset_type='image',
    source_key=f'guardrail-temp/{asset_hash}',
    status='active',
    metadata_json={'temporary_guardrail_test': True},
)
version = AssetVersion.objects.create(
    asset=asset,
    version_number=1,
    content_uri=str(asset_path),
    content_hash=asset_hash,
    mime_type='image/jpeg',
    size_bytes=asset_path.stat().st_size,
    provenance_json={'temporary_guardrail_test': True},
)
draft = PublicationDraft.objects.create(
    organization=organization,
    company=company,
    asset=asset,
    asset_version=version,
    title='Guardrail temporary approved draft',
    channel='instagram',
    body=published_post['caption'],
    status='approved',
    idempotency_key='guardrail-temp-approved-draft',
    metadata_json={
        'explicit_user_approval': True,
        'blocked_asset_sha256': [],
        'temporary_guardrail_test': True,
    },
)
try:
    test_post = {**published_post, 'idempotency_key': draft.idempotency_key}
    valid = mod.validate_backend_approval(test_post, asset_hash)
    missing = mod.validate_backend_approval({**published_post, 'idempotency_key': 'missing-draft-for-guardrail-test'}, asset_hash)
    wrong_hash = mod.validate_backend_approval(test_post, '0' * 64)
    wrong_caption = mod.validate_backend_approval({**test_post, 'caption': 'mutated caption'}, asset_hash)
    result = {
        'valid_approved_draft_accepted': valid,
        'missing_draft_rejected': missing,
        'wrong_hash_rejected': wrong_hash,
        'wrong_caption_rejected': wrong_caption,
        'pass': valid.get('ok') is True and missing.get('ok') is False and wrong_hash.get('ok') is False and wrong_caption.get('ok') is False,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result['pass']:
        raise SystemExit(1)
finally:
    draft.delete()
    version.delete()
    asset.delete()
