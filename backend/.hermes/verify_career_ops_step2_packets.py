import json
from pathlib import Path

from infrastructure.orm.models import AssetVersion, CompanyOpportunity, ServiceDeliverable

payload = json.loads(Path('/app/.hermes/career_ops_step2_packets_20260617.json').read_text(encoding='utf-8'))
print('company_id', payload['company_id'])
print('base_cv_asset_id', payload['base_cv_asset_id'])
print('result_count', len(payload['results']))
for item in payload['results']:
    opportunity = CompanyOpportunity.objects.get(id=item['opportunity_id'])
    deliverables = ServiceDeliverable.objects.filter(
        company_id=payload['company_id'],
        metadata_json__career_ops__opportunity_id=item['opportunity_id'],
    ).order_by('deliverable_type', '-updated_at')
    types = sorted({deliverable.deliverable_type for deliverable in deliverables})
    packet = AssetVersion.objects.get(id=item['packet_asset_version_id']).provenance_json['career_ops']
    resume = packet['artifacts']['tailored_resume']
    cover = packet['artifacts']['cover_letter']
    print('\nOPPORTUNITY', opportunity.title)
    print('deliverable_types', types)
    print('resume_version', item['tailored_resume_asset_version_id'])
    print('cover_version', item['cover_letter_asset_version_id'])
    print('packet_version', item['packet_asset_version_id'])
    print('readiness_blockers', item['readiness']['blockers'])
    print('resume_sections', [section['heading'] for section in resume['sections']])
    print('resume_preview', resume['plain_text'][:260].replace('\n', ' | '))
    print('cover_preview', ' '.join(cover['paragraphs'])[:260])
    print('side_effects', packet['quality']['external_side_effects_allowed'], resume['quality']['external_side_effects_allowed'], cover['quality']['external_side_effects_allowed'])
