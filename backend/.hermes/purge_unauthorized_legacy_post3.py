from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from infrastructure.orm.models import Asset, AssetVersion, MediaGenerationJob, PublicationDraft

ROOT = Path('.').resolve()
HERMES = ROOT / '.hermes'
SCHEDULE_PATH = HERMES / 'legacy_optical_noir_autopublish' / 'schedule.json'
RECEIPT_PATH = HERMES / 'legacy_optical_noir_autopublish' / 'unauthorized_post3_purge_receipt.json'
POST_NUM = 3
IDEMPOTENCY_KEY = 'legacy-optical-noir-20260629-day-3'
TARGET_BASENAMES = {
    'legacy_optical_noir_post_03.png',
    'legacy_optical_noir_post_03.jpg',
    'legacy_optical_noir_post_03.jpeg',
    'legacy_noir_post_03_branded.jpg',
}
KEEP_NAME_FRAGMENTS = {'replacement'}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def delete_path(path: Path, deleted: list[dict]) -> None:
    if not path.exists() or not path.is_file():
        return
    deleted.append({'path': str(path), 'sha256': sha256(path), 'size': path.stat().st_size})
    path.unlink()

def zip_contains_unauthorized(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as zf:
            return any(Path(name).name in TARGET_BASENAMES for name in zf.namelist())
    except Exception:
        return False

receipt = {
    'created_at': datetime.now(timezone.utc).isoformat(),
    'post': POST_NUM,
    'idempotency_key': IDEMPOTENCY_KEY,
    'deleted_files': [],
    'deleted_zip_packages': [],
    'db_deleted': {},
    'schedule_update': {},
    'replacement_candidates_preserved': [],
    'contains_no_image_bytes': True,
}

# Remove active/autopublish schedule reference so no future worker can touch it.
schedule = json.loads(SCHEDULE_PATH.read_text(encoding='utf-8'))
old_posts = list(schedule.get('posts') or [])
removed_posts = [p for p in old_posts if int(p.get('post') or 0) == POST_NUM]
schedule['posts'] = [p for p in old_posts if int(p.get('post') or 0) != POST_NUM]
schedule['status'] = 'paused_unauthorized_asset_purged'
schedule.setdefault('removed_posts', [])
for p in removed_posts:
    schedule['removed_posts'].append({
        'post': POST_NUM,
        'removed_at': datetime.now(timezone.utc).isoformat(),
        'reason': 'unauthorized_asset_purged_after_client_report',
        'provider_media_id': p.get('provider_media_id') or '',
        'provider_permalink': p.get('provider_permalink') or '',
        'scheduled_at': p.get('scheduled_at') or '',
        'published_at': p.get('published_at') or '',
        'asset_filename': p.get('asset_filename') or '',
    })
receipt['schedule_update'] = {
    'removed_active_posts': len(removed_posts),
    'remaining_posts': [p.get('post') for p in schedule.get('posts', [])],
    'status': schedule['status'],
}
SCHEDULE_PATH.write_text(json.dumps(schedule, indent=2, ensure_ascii=False), encoding='utf-8')

# Delete local image files everywhere under backend .hermes except replacement candidates.
for path in HERMES.rglob('*'):
    if not path.is_file():
        continue
    name = path.name.lower()
    if any(fragment in name for fragment in KEEP_NAME_FRAGMENTS):
        if 'post_03' in name:
            receipt['replacement_candidates_preserved'].append(str(path))
        continue
    if name in TARGET_BASENAMES:
        delete_path(path, receipt['deleted_files'])

# Delete zip packages that still contain the unauthorized post_03 asset.
zip_roots = [HERMES, Path.home() / 'Downloads']
seen = set()
for root in zip_roots:
    if not root.exists():
        continue
    for zip_path in root.rglob('*.zip'):
        if zip_path in seen:
            continue
        seen.add(zip_path)
        if zip_contains_unauthorized(zip_path):
            receipt['deleted_zip_packages'].append({'path': str(zip_path), 'sha256': sha256(zip_path), 'size': zip_path.stat().st_size})
            zip_path.unlink()

# Remove DB records for the unauthorized image/draft. Delete the draft first, then asset/version/job if present.
draft = PublicationDraft.objects.filter(idempotency_key=IDEMPOTENCY_KEY).first()
if draft is not None:
    asset_id = str(draft.asset_id) if draft.asset_id else ''
    asset_version_id = str(draft.asset_version_id) if draft.asset_version_id else ''
    media_job_id = str(draft.media_job_id) if draft.media_job_id else ''
    receipt['db_deleted']['publication_draft'] = {'id': str(draft.id), 'status': draft.status, 'asset_id': asset_id, 'asset_version_id': asset_version_id, 'media_job_id': media_job_id}
    draft.delete()
    if asset_version_id:
        deleted, _ = AssetVersion.objects.filter(id=asset_version_id).delete()
        receipt['db_deleted']['asset_version_deleted_count'] = deleted
    if asset_id:
        deleted, _ = Asset.objects.filter(id=asset_id).delete()
        receipt['db_deleted']['asset_deleted_count'] = deleted
    if media_job_id:
        deleted, _ = MediaGenerationJob.objects.filter(id=media_job_id).delete()
        receipt['db_deleted']['media_job_deleted_count'] = deleted
else:
    receipt['db_deleted']['publication_draft'] = None

RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps(receipt, indent=2, ensure_ascii=False))
