from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from django.utils import timezone

from application.services.career_ops_engagements import ensure_career_ops_application_engagement
from infrastructure.orm.models import Asset, AssetVersion, Graph, ServiceDeliverable, User

company = Graph.objects.get(id='95f3e98b-8e14-4511-bdb1-563121c1950e')
user = User.objects.get(email='careerops.operator@forgegraph.local')
engagement = ensure_career_ops_application_engagement(company=company, actor=user)
zip_path = Path('/app/.hermes/career_ops_e2e_delivery/20260629-125100-certidentityfixed/careerops-daily-review-package-20260629.zip')
content = zip_path.read_bytes()
digest = hashlib.sha256(content).hexdigest()
source_key = 'career_ops:daily_review_package:2026-06-29'
asset, _ = Asset.objects.get_or_create(
    company=company,
    source_key=source_key,
    defaults={
        'organization': company.organization,
        'title': 'CareerOps daily review package — 2026-06-29',
        'asset_type': 'document',
        'created_by_type': 'system',
        'metadata_json': {},
    },
)
asset.organization = company.organization
asset.title = 'CareerOps daily review package — 2026-06-29'
asset.asset_type = 'document'
asset.metadata_json = {
    'career_ops': {
        'deliverable_type': 'daily_review_package_zip',
        'run_date': '2026-06-29',
        'external_side_effects_allowed': False,
        'whatsapp_text_message_id': '3EB006AF59DA4B52282EA4',
        'whatsapp_zip_media_message_id': '3EB0E7CF71A5D0574F71A7',
    }
}
asset.save()
version = AssetVersion.objects.filter(asset=asset, content_hash=digest).first()
if version is None:
    latest = AssetVersion.objects.filter(asset=asset).order_by('-version_number').values_list('version_number', flat=True).first() or 0
    version = AssetVersion.objects.create(
        asset=asset,
        version_number=latest + 1,
        content_uri='forgegraph://career-ops/daily-review-package/2026-06-29.zip',
        content_hash=digest,
        mime_type='application/zip',
        size_bytes=len(content),
        provenance_json={
            'career_ops': asset.metadata_json['career_ops'] | {
                'content_hash': digest,
                'size_bytes': len(content),
                'package_path': str(zip_path),
            },
            'inline_content_base64': base64.b64encode(content).decode('ascii'),
        },
    )
deliverable, _ = ServiceDeliverable.objects.get_or_create(
    company=company,
    engagement=engagement,
    deliverable_type='daily_review_package_zip',
    artifact=asset,
    defaults={
        'organization': company.organization,
        'title': asset.title,
        'visibility': 'operator',
    },
)
deliverable.organization = company.organization
deliverable.title = asset.title
deliverable.status = 'in_review'
deliverable.visibility = 'operator'
deliverable.summary = 'CareerOps daily review ZIP package for 2026-06-29; delivered to WhatsApp for review.'
deliverable.metadata_json = {
    'career_ops': {
        'asset_version_id': str(version.id),
        'run_date': '2026-06-29',
        'external_side_effects_allowed': False,
        'whatsapp_text_message_id': '3EB006AF59DA4B52282EA4',
        'whatsapp_zip_media_message_id': '3EB0E7CF71A5D0574F71A7',
        'persisted_at': timezone.now().isoformat(),
    }
}
deliverable.save()
asset.origin_deliverable_id = deliverable.id
asset.save(update_fields=['origin_deliverable_id', 'updated_at'])
print({'deliverable_id': str(deliverable.id), 'asset_version_id': str(version.id), 'size_bytes': version.size_bytes})
