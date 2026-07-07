from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from application.services.career_ops_engagements import ensure_career_ops_application_engagement
from infrastructure.orm.models import Asset, AssetVersion, Graph, ServiceDeliverable, User

BASE = Path('/app/.hermes/career_ops_kiddom_20260702')
RUN_DATE = '2026-07-02'
company, _ = Graph.objects.get_or_create(
    name='CareerOps ForgeGraph Company',
    defaults={'description': 'CareerOps durable company context for Miguel Athie application work.'},
)
user, _ = User.objects.get_or_create(email='careerops.operator@forgegraph.local', defaults={'full_name': 'CareerOps Operator'})
engagement = ensure_career_ops_application_engagement(company=company, actor=user)

files = [
    ('job_posting_snapshot', 'kiddom-fit-evaluation.json', 'application/json', 'Kiddom / TurnKey job fit evaluation'),
    ('tailored_cv_markdown', 'Miguel-Athie-Kiddom-Senior-Backend-Engineer-CV.md', 'text/markdown', 'Miguel Athie - Kiddom tailored CV Markdown'),
    ('tailored_cv_pdf', 'Miguel-Athie-Kiddom-Senior-Backend-Engineer-CV.pdf', 'application/pdf', 'Miguel Athie - Kiddom tailored CV PDF'),
    ('cover_letter_markdown', 'Miguel-Athie-Kiddom-Senior-Backend-Engineer-Cover-Letter.md', 'text/markdown', 'Miguel Athie - Kiddom cover letter Markdown'),
    ('cover_letter_pdf', 'Miguel-Athie-Kiddom-Senior-Backend-Engineer-Cover-Letter.pdf', 'application/pdf', 'Miguel Athie - Kiddom cover letter PDF'),
]
created=[]
for dtype, filename, mime, title in files:
    path = BASE / filename
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    source_key = f'career_ops:kiddom_turnkey:{RUN_DATE}:{dtype}'
    asset, _ = Asset.objects.get_or_create(
        company=company,
        source_key=source_key,
        defaults={
            'organization': company.organization,
            'title': title,
            'asset_type': 'document',
            'created_by_type': 'system',
            'metadata_json': {},
        },
    )
    asset.organization = company.organization
    asset.title = title
    asset.asset_type = 'document'
    asset.metadata_json = {
        'career_ops': {
            'deliverable_type': dtype,
            'target_company': 'Kiddom',
            'recruiter': 'TurnKey Tech Staffing',
            'role_title': 'Senior Backend Engineer (Python/Go)',
            'source_url': 'https://mx.thebigjobsite.com/details/395F52E66FD1C65572E43F694028C382/senior-backend-engineer--python-go',
            'run_date': RUN_DATE,
            'external_side_effects_allowed': False,
        }
    }
    asset.save()
    version = AssetVersion.objects.filter(asset=asset, content_hash=digest).first()
    if version is None:
        latest = AssetVersion.objects.filter(asset=asset).order_by('-version_number').values_list('version_number', flat=True).first() or 0
        version = AssetVersion.objects.create(
            asset=asset,
            version_number=latest + 1,
            content_uri=f'forgegraph://career-ops/kiddom-turnkey/{RUN_DATE}/{filename}',
            content_hash=digest,
            mime_type=mime,
            size_bytes=len(content),
            provenance_json={
                'career_ops': asset.metadata_json['career_ops'] | {'content_hash': digest, 'size_bytes': len(content), 'filename': filename},
                'inline_content_base64': base64.b64encode(content).decode('ascii'),
            },
        )
    deliverable, _ = ServiceDeliverable.objects.get_or_create(
        company=company,
        engagement=engagement,
        deliverable_type=dtype,
        artifact=asset,
        defaults={
            'organization': company.organization,
            'title': title,
            'visibility': 'operator',
        },
    )
    deliverable.organization = company.organization
    deliverable.title = title
    deliverable.status = 'in_review'
    deliverable.visibility = 'operator'
    deliverable.summary = f'CareerOps Kiddom/TurnKey {dtype} for manual review.'
    deliverable.metadata_json = {
        'career_ops': {
            'asset_version_id': str(version.id),
            'target_company': 'Kiddom',
            'recruiter': 'TurnKey Tech Staffing',
            'role_title': 'Senior Backend Engineer (Python/Go)',
            'run_date': RUN_DATE,
            'external_side_effects_allowed': False,
        }
    }
    deliverable.save()
    asset.origin_deliverable_id = deliverable.id
    asset.save(update_fields=['origin_deliverable_id', 'updated_at'])
    created.append({'deliverable_type': dtype, 'deliverable_id': str(deliverable.id), 'asset_version_id': str(version.id), 'size_bytes': version.size_bytes})
print(json.dumps({'company_id': str(company.id), 'created': created}, indent=2))
