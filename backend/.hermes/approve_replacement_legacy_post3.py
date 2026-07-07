from __future__ import annotations

import hashlib
import json
import shutil
from datetime import timedelta
from pathlib import Path

from django.utils import timezone

from infrastructure.orm.models import Asset, AssetVersion, PublicationDraft

ROOT = Path('.').resolve()
SCHEDULE_PATH = ROOT / '.hermes' / 'legacy_optical_noir_autopublish' / 'schedule.json'
SOURCE = ROOT / '.hermes' / 'legacy_campaign_report_first_run' / 'replacement_assets' / 'legacy_optical_noir_post_03_replacement_branded.jpg'
ASSET_DIR = ROOT / '.hermes' / 'legacy_optical_noir_autopublish' / 'assets'
DEST = ASSET_DIR / 'legacy_optical_noir_post_03_replacement_authorized.jpg'
IDEMPOTENCY_KEY = 'legacy-optical-noir-20260629-day-3-replacement-authorized'
CAPTION = (
    'Más intención. Menos ruido.\n\n'
    'Legacy Optical Noir destaca lo importante: forma, claridad y presencia, con una paleta sobria de negro, marfil y acentos cálidos.\n\n'
    'Guarda este post si este es tu estilo.\n\n'
    '#LegacyEffect #OpticalNoir #EyewearStyle #VisionConEstilo'
)
APPROVAL_NOTE = 'Mike explicitly authorized publishing the replacement Legacy Optical Noir post after unauthorized post 3 was purged.'

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

if not SOURCE.exists():
    raise SystemExit(f'replacement source missing: {SOURCE}')
ASSET_DIR.mkdir(parents=True, exist_ok=True)
shutil.copy2(SOURCE, DEST)
asset_hash = sha256(DEST)
asset_size = DEST.stat().st_size

schedule = json.loads(SCHEDULE_PATH.read_text(encoding='utf-8'))
blocked = [h for h in schedule.get('blocked_asset_sha256', []) if h != asset_hash]
schedule['blocked_asset_sha256'] = blocked
company = PublicationDraft.objects.exclude(company=None).order_by('-updated_at').first().company
organization = company.organization
if organization is None:
    raise SystemExit('company has no organization')
asset, _ = Asset.objects.update_or_create(
    company=company,
    source_key=f'legacy-optical-noir/post-03-replacement/{asset_hash}',
    defaults={
        'organization': organization,
        'title': 'Legacy Optical Noir Day 3 authorized replacement',
        'asset_type': 'image',
        'created_by_type': 'user',
        'status': 'active',
        'metadata_json': {
            'campaign': 'Legacy Optical Noir',
            'post': 3,
            'replacement_for_media_id': '18086310779431351',
            'authorized_replacement': True,
            'approval_note': APPROVAL_NOTE,
            'local_path': str(DEST),
            'sha256': asset_hash,
        },
    },
)
version, _ = AssetVersion.objects.update_or_create(
    asset=asset,
    content_hash=asset_hash,
    defaults={
        'version_number': 1,
        'content_uri': str(DEST),
        'mime_type': 'image/jpeg',
        'size_bytes': asset_size,
        'provenance_json': {
            'source_path': str(SOURCE),
            'approval_source': APPROVAL_NOTE,
            'guardrail': 'hash-bound backend approval required before publish',
        },
    },
)
now = timezone.now()
draft, _ = PublicationDraft.objects.update_or_create(
    company=company,
    idempotency_key=IDEMPOTENCY_KEY,
    defaults={
        'organization': organization,
        'requested_by': None,
        'approved_by': None,
        'asset': asset,
        'asset_version': version,
        'media_job': None,
        'title': 'Legacy Optical Noir Day 3 authorized replacement',
        'channel': 'instagram',
        'audience': 'Legacy Instagram audience',
        'body': CAPTION,
        'call_to_action': 'Guarda este post si este es tu estilo.',
        'status': 'approved',
        'approved_at': now,
        'published_at': None,
        'metadata_json': {
            'campaign': 'Legacy Optical Noir',
            'post': 3,
            'replacement_for_media_id': '18086310779431351',
            'replacement_for_permalink': 'https://www.instagram.com/p/DaRU3QNINLs/',
            'explicit_user_approval': True,
            'approval_source': APPROVAL_NOTE,
            'approved_asset_sha256': asset_hash,
            'blocked_asset_sha256': schedule.get('blocked_asset_sha256', []),
            'guardrail_version': 'backend-approval-hash-v1',
            'authorized_asset_path': str(DEST),
            'autopublish_schedule': {},
        },
    },
)
post = {
    'post': 3,
    'status': 'approved',
    'platform': 'instagram',
    'provider': 'meta_graph',
    'account_id_env': 'META_GRAPH_IG_USER_ID_ALLOWLIST',
    'asset_path': str(DEST),
    'asset_filename': DEST.name,
    'asset_sha256': asset_hash,
    'caption': CAPTION,
    'caption_sha256': hashlib.sha256(CAPTION.encode('utf-8')).hexdigest(),
    'scheduled_at': (timezone.localtime(now) - timedelta(minutes=1)).isoformat(),
    'timezone': 'America/Mexico_City',
    'idempotency_key': IDEMPOTENCY_KEY,
    'backend_publication_draft_id': str(draft.id),
    'approval_source': APPROVAL_NOTE,
    'published_at': None,
    'provider_media_id': '',
    'provider_permalink': '',
    'replacement_for_media_id': '18086310779431351',
    'replacement_for_permalink': 'https://www.instagram.com/p/DaRU3QNINLs/',
    'last_error': {},
}
posts = [p for p in schedule.get('posts', []) if int(p.get('post') or 0) != 3 and p.get('idempotency_key') != IDEMPOTENCY_KEY]
inserted = False
out = []
for p in posts:
    if not inserted and int(p.get('post') or 99) > 3:
        out.append(post)
        inserted = True
    out.append(p)
if not inserted:
    out.append(post)
schedule['posts'] = out
schedule['status'] = 'active_guarded_manual_replacement'
schedule['guardrail_version'] = 'backend-approval-hash-v1'
schedule['autopublish_paused_reason'] = 'Manual replacement publish in progress; cron remains paused until verified.'
schedule['replacement_candidates'] = [c for c in schedule.get('replacement_candidates', []) if c.get('asset_path') != str(SOURCE)]
draft.metadata_json['autopublish_schedule'] = post
draft.save(update_fields=['metadata_json', 'updated_at'])
SCHEDULE_PATH.write_text(json.dumps(schedule, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps({
    'ok': True,
    'draft_id': str(draft.id),
    'asset_id': str(asset.id),
    'asset_version_id': str(version.id),
    'asset_path': str(DEST),
    'asset_sha256': asset_hash,
    'blocked_contains_authorized_hash': asset_hash in schedule.get('blocked_asset_sha256', []),
    'schedule_status': schedule['status'],
}, indent=2))
