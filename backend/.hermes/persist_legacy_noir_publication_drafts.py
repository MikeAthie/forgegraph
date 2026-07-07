from pathlib import Path
import json
from django.utils import timezone
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    Graph,
    MediaGenerationJob,
    PublicationDraft,
    User,
)

sched = json.loads(Path('.hermes/legacy_optical_noir_autopublish/schedule.json').read_text(encoding='utf-8'))
manifest = json.loads(Path('.hermes/forgegraph_atlas_prompt_runs/atlas_prompt_codex_media_20260615_223301/client_package/manifest.json').read_text(encoding='utf-8'))
company = Graph.objects.get(name='Legacy')
org = company.organization
user = User.objects.first()
created = 0
updated = 0
rows = []
media_by_post = {int(m['post']): m for m in manifest.get('media', [])}

for post in sched['posts']:
    m = media_by_post.get(int(post['post']), {})
    asset = Asset.objects.filter(id=m.get('asset_id')).first()
    av = AssetVersion.objects.filter(id=m.get('asset_version_id')).first()
    mj = MediaGenerationJob.objects.filter(id=m.get('media_generation_job_id')).first()
    defaults = {
        'organization': org,
        'requested_by': user,
        'approved_by': user,
        'asset': asset,
        'asset_version': av,
        'media_job': mj,
        'title': f"Legacy Optical Noir Day {post['post']}",
        'channel': 'instagram',
        'audience': 'Legacy Instagram followers / CDMX eyewear prospects',
        'body': post['caption'],
        'call_to_action': 'Enviar DM para conocer estilos disponibles',
        'status': 'approved',
        'approved_at': timezone.now(),
        'metadata_json': {
            'autopublish_schedule': post,
            'calendar_rebased_day_1': sched['day_1_date'],
            'package_sha256': sched['package_sha256'],
            'approval_source': 'Mike approved official-logo package and requested automatic publication with today as Day 1.',
        },
    }
    draft, was_created = PublicationDraft.objects.get_or_create(
        company=company,
        idempotency_key=post['idempotency_key'],
        defaults=defaults,
    )
    if was_created:
        created += 1
    else:
        draft.status = 'approved'
        draft.approved_by = user
        draft.approved_at = draft.approved_at or timezone.now()
        draft.body = post['caption']
        draft.asset = asset
        draft.asset_version = av
        draft.media_job = mj
        meta = dict(draft.metadata_json or {})
        meta.update(defaults['metadata_json'])
        draft.metadata_json = meta
        draft.save(update_fields=['status', 'approved_by', 'approved_at', 'body', 'asset', 'asset_version', 'media_job', 'metadata_json', 'updated_at'])
        updated += 1
    rows.append({'post': post['post'], 'draft_id': str(draft.id), 'status': draft.status, 'scheduled_at': post['scheduled_at']})

print(json.dumps({'created': created, 'updated': updated, 'rows': rows}, indent=2))
