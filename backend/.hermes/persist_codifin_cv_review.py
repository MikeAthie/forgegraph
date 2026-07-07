from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.utils import timezone

from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    CompanyOpportunity,
    CompanySignal,
    Graph,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    User,
)

ROOT = Path('/app/.hermes')
COMPANY_NAME = 'CareerOps ForgeGraph Company'
OPERATOR_EMAIL = 'careerops.operator@forgegraph.local'
SOURCE_KEY = 'careerops-codifin-cv-review-20260628'

files = {
    'user_benchmark_cv': ROOT / 'codifin-user-benchmark-cv.txt',
    'forgegraph_v2_cv': ROOT / 'codifin-cv-draft-v2.txt',
    'forgegraph_v2_cover_letter': ROOT / 'codifin-cover-letter-draft-v2.txt',
    'comparison_report': ROOT / 'codifin-cv-comparison-report.json',
}

company = Graph.objects.get(name=COMPANY_NAME)
organization = company.organization
operator = User.objects.get(email=OPERATOR_EMAIL)

catalog, _ = ServiceCatalogItem.objects.get_or_create(
    organization=organization,
    slug='careerops-cv-comparison-remake',
    defaults={
        'title': 'CareerOps CV comparison and remake',
        'description': 'Compare candidate CV variants against a target posting and persist improved drafts.',
        'status': 'active',
        'visibility': 'organization',
        'audience': 'operator',
        'created_by': operator,
    },
)
catalog.title = 'CareerOps CV comparison and remake'
catalog.description = 'Compare candidate CV variants against a target posting and persist improved drafts.'
catalog.status = 'active'
catalog.visibility = 'organization'
catalog.save()

engagement, _ = ServiceEngagement.objects.get_or_create(
    company=company,
    source_key=SOURCE_KEY,
    defaults={
        'organization': organization,
        'catalog_item': catalog,
        'status': 'in_review',
        'customer_status': 'review_ready',
        'requested_by': operator,
        'assigned_operator': operator,
    },
)
engagement.organization = organization
engagement.catalog_item = catalog
engagement.status = 'in_review'
engagement.customer_status = 'review_ready'
engagement.public_summary = 'Codifin CV benchmark comparison and improved ForgeGraph v2 draft are ready for Mike review.'
engagement.internal_notes = 'Created after user corrected that E2E CareerOps CV work must persist in ForgeGraph company state.'
engagement.metadata_json = {
    'source': SOURCE_KEY,
    'job_url': 'https://mx.indeed.com/viewjob?jk=0ee36499821e9442',
    'company': 'Codifin',
    'role': 'Lead Golang & React Developer CDMX Bilingüe',
    'candidate_correction': 'Cambridge English C2 Proficiency certificate is source-backed.',
    'employer_submit_side_effects_allowed': False,
}
engagement.assigned_operator = operator
engagement.requested_by = operator
engagement.save()

signal, _ = CompanySignal.objects.get_or_create(
    company=company,
    source='indeed',
    external_key='indeed:0ee36499821e9442:cv-review',
    defaults={
        'organization': organization,
        'created_by': operator,
        'signal_type': 'lead',
        'signal_kind': 'opportunity',
        'domain_context': 'career_ops',
        'status': 'qualified',
        'title': 'Codifin Lead Golang & React Developer CV review',
        'summary': 'User requested ForgeGraph-backed comparison/remake for Codifin Indeed posting.',
        'channel': 'indeed',
    },
)
signal.organization = organization
signal.created_by = operator
signal.signal_type = 'lead'
signal.signal_kind = 'opportunity'
signal.domain_context = 'career_ops'
signal.status = 'qualified'
signal.title = 'Codifin Lead Golang & React Developer CV review'
signal.summary = 'ForgeGraph-backed comparison between user benchmark CV and improved v2 CV with Cambridge C2 fact.'
signal.channel = 'indeed'
signal.metadata_json = engagement.metadata_json
signal.save()

opportunity, _ = CompanyOpportunity.objects.get_or_create(
    company=company,
    external_key='indeed:0ee36499821e9442:codifin-lead-golang-react',
    defaults={
        'organization': organization,
        'signal': signal,
        'owner_user': operator,
        'status': 'qualified',
        'title': 'Codifin — Lead Golang & React Developer CDMX Bilingüe',
        'summary': 'Hybrid CDMX Lead Full-Stack role: React, Golang, PostgreSQL, SaaS/data automation, AI integrations, English C1 required.',
        'channel': 'indeed',
        'currency': 'mxn',
        'estimated_value_amount': 90000,
        'next_action': 'Review exact v2 CV and cover letter before any employer-facing action.',
    },
)
opportunity.organization = organization
opportunity.signal = signal
opportunity.owner_user = operator
opportunity.status = 'qualified'
opportunity.metadata_json = engagement.metadata_json
opportunity.save()


def persist_text(deliverable_type: str, title: str, path: Path, mime_type: str = 'text/plain'):
    content = path.read_text(encoding='utf-8')
    data = content.encode('utf-8')
    digest = hashlib.sha256(data).hexdigest()
    asset, _ = Asset.objects.get_or_create(
        company=company,
        source_key=f'{SOURCE_KEY}:{deliverable_type}',
        defaults={
            'organization': organization,
            'title': title,
            'asset_type': 'career_ops_deliverable',
            'created_by_type': 'agent',
            'created_by_id': operator.id,
        },
    )
    asset.organization = organization
    asset.title = title
    asset.asset_type = 'career_ops_deliverable'
    asset.status = 'active'
    asset.metadata_json = {
        'source': SOURCE_KEY,
        'deliverable_type': deliverable_type,
        'opportunity_id': str(opportunity.id),
        'inline_preview': content[:1000],
    }
    asset.save()
    version = AssetVersion.objects.filter(asset=asset, content_hash=digest).first()
    if version is None:
        latest = AssetVersion.objects.filter(asset=asset).order_by('-version_number').values_list('version_number', flat=True).first() or 0
        version = AssetVersion.objects.create(
            asset=asset,
            version_number=int(latest) + 1,
            content_uri=f'forgegraph://careerops/codifin-cv-review/{deliverable_type}.txt',
            content_hash=digest,
            mime_type=mime_type,
            size_bytes=len(data),
            provenance_json={
                'source': SOURCE_KEY,
                'inline_content': content,
                'generated_at': timezone.now().isoformat(),
                'job_url': 'https://mx.indeed.com/viewjob?jk=0ee36499821e9442',
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
    deliverable.summary = content[:240]
    deliverable.metadata_json = {
        'source': SOURCE_KEY,
        'asset_version_id': str(version.id),
        'opportunity_id': str(opportunity.id),
        'approval_required_before_employer_submission': True,
    }
    deliverable.created_by = operator
    deliverable.save()
    asset.origin_deliverable_id = deliverable.id
    asset.save(update_fields=['origin_deliverable_id', 'updated_at'])
    return deliverable, version

created = {}
for dtype, path in files.items():
    title = {
        'user_benchmark_cv': 'Codifin user benchmark CV',
        'forgegraph_v2_cv': 'Codifin improved ForgeGraph v2 CV',
        'forgegraph_v2_cover_letter': 'Codifin improved ForgeGraph v2 cover letter',
        'comparison_report': 'Codifin CV comparison report',
    }[dtype]
    mime = 'application/json' if dtype == 'comparison_report' else 'text/plain'
    deliverable, version = persist_text(dtype, title, path, mime)
    created[dtype] = {'deliverable_id': str(deliverable.id), 'asset_version_id': str(version.id)}

print(json.dumps({
    'status': 'ok',
    'company_id': str(company.id),
    'company_name': company.name,
    'engagement_id': str(engagement.id),
    'signal_id': str(signal.id),
    'opportunity_id': str(opportunity.id),
    'deliverables': created,
    'employer_submit_side_effects_allowed': False,
}, indent=2, sort_keys=True))
