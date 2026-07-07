from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from django.utils import timezone

from infrastructure.orm.models import Asset, AssetVersion, Graph, ServiceDeliverable, ServiceEngagement, User

ROOT = Path('/app/.hermes')
COMPANY_NAME = 'CareerOps ForgeGraph Company'
OPERATOR_EMAIL = 'careerops.operator@forgegraph.local'
ENGAGEMENT_SOURCE_KEY = 'careerops-codifin-cv-review-20260628'
SOURCE_KEY = 'careerops-codifin-final-review-pdf-20260628'

company = Graph.objects.get(name=COMPANY_NAME)
organization = company.organization
operator = User.objects.get(email=OPERATOR_EMAIL)
engagement = ServiceEngagement.objects.get(company=company, source_key=ENGAGEMENT_SOURCE_KEY)

def persist_binary(*, deliverable_type: str, title: str, path: Path, mime_type: str):
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    asset, _ = Asset.objects.get_or_create(
        company=company,
        source_key=f'{SOURCE_KEY}:{deliverable_type}',
        defaults={
            'organization': organization,
            'title': title,
            'asset_type': 'career_ops_pdf',
            'created_by_type': 'agent',
            'created_by_id': operator.id,
        },
    )
    asset.organization = organization
    asset.title = title
    asset.asset_type = 'career_ops_pdf'
    asset.status = 'active'
    asset.metadata_json = {
        'source': SOURCE_KEY,
        'deliverable_type': deliverable_type,
        'job_url': 'https://mx.indeed.com/viewjob?jk=0ee36499821e9442',
        'public_forgegraph_repo_verified': 'https://github.com/MikeAthie/ForgeGraph',
        'employer_submit_side_effects_allowed': False,
    }
    asset.save()
    version = AssetVersion.objects.filter(asset=asset, content_hash=digest).first()
    if version is None:
        latest = AssetVersion.objects.filter(asset=asset).order_by('-version_number').values_list('version_number', flat=True).first() or 0
        version = AssetVersion.objects.create(
            asset=asset,
            version_number=int(latest) + 1,
            content_uri=f'forgegraph://careerops/codifin-final-review/{path.name}',
            content_hash=digest,
            mime_type=mime_type,
            size_bytes=len(data),
            provenance_json={
                'source': SOURCE_KEY,
                'inline_content_base64': base64.b64encode(data).decode('ascii'),
                'generated_at': timezone.now().isoformat(),
                'job_url': 'https://mx.indeed.com/viewjob?jk=0ee36499821e9442',
                'parseability_report': json.loads((ROOT / 'codifin-final-review-cv-parseability.json').read_text(encoding='utf-8')) if (ROOT / 'codifin-final-review-cv-parseability.json').exists() else {},
                'visual_review': 'Rendered to PNG pages and visually inspected for readability, single-column layout, no overlap/cutoff.',
                'employer_submit_side_effects_allowed': False,
            },
        )
    deliverable, _ = ServiceDeliverable.objects.get_or_create(
        engagement=engagement,
        deliverable_type=deliverable_type,
        defaults={'organization': organization, 'company': company, 'created_by': operator},
    )
    deliverable.organization = organization
    deliverable.company = company
    deliverable.title = title
    deliverable.status = 'in_review'
    deliverable.visibility = 'operator'
    deliverable.artifact = asset
    deliverable.summary = 'Final-review PDF for Codifin Lead Golang & React Developer CV. Awaiting Mike approval before employer-facing action.'
    deliverable.metadata_json = {
        'source': SOURCE_KEY,
        'asset_version_id': str(version.id),
        'approval_required_before_employer_submission': True,
        'employer_submit_side_effects_allowed': False,
    }
    deliverable.created_by = operator
    deliverable.save()
    asset.origin_deliverable_id = deliverable.id
    asset.save(update_fields=['origin_deliverable_id', 'updated_at'])
    return deliverable, version

pdf_deliverable, pdf_version = persist_binary(
    deliverable_type='codifin_final_review_cv_pdf',
    title='Codifin final-review CV PDF',
    path=ROOT / 'codifin-final-review-cv.pdf',
    mime_type='application/pdf',
)

print(json.dumps({
    'status': 'ok',
    'company_id': str(company.id),
    'engagement_id': str(engagement.id),
    'pdf_deliverable_id': str(pdf_deliverable.id),
    'pdf_asset_version_id': str(pdf_version.id),
    'pdf_size_bytes': pdf_version.size_bytes,
    'employer_submit_side_effects_allowed': False,
}, indent=2, sort_keys=True))
