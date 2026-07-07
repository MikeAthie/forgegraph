import json
from pathlib import Path

from infrastructure.orm.models import AssetVersion, CompanyOpportunity, ServiceDeliverable

payload = json.loads(Path('/app/.hermes/career_ops_ats_packets_20260617.json').read_text(encoding='utf-8'))
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
    ats_inline = packet['artifacts']['ats_simulation']
    ats_version = AssetVersion.objects.get(id=item['ats_simulation_asset_version_id']).provenance_json['career_ops']
    print('\nOPPORTUNITY', opportunity.title)
    print('deliverable_types', types)
    print('packet_version', item['packet_asset_version_id'])
    print('resume_version', item['tailored_resume_asset_version_id'])
    print('cover_version', item['cover_letter_asset_version_id'])
    print('ats_version', item['ats_simulation_asset_version_id'])
    print('ats_score_inline', ats_inline['atsScore'], ats_inline['scoreBand'], ats_inline['thresholds'])
    print('ats_score_deliverable', ats_version['atsScore'], ats_version['scoreBand'], ats_version['thresholds'])
    print('ats_quality', ats_version['quality'])
    print('readiness_blockers', item['readiness']['blockers'])
    print('ats_checks', {k: v for k, v in item['readiness']['checks'].items() if k.startswith('ats_')})
    required = {'application_packet', 'tailored_resume_html', 'cover_letter_draft', 'ats_simulation_report', 'job_evaluation_report', 'job_liveness_receipt'}
    assert required <= set(types), required - set(types)
    assert ats_inline['format'] == 'career_ops_ats_simulation_v1'
    assert ats_version['format'] == 'career_ops_ats_simulation_v1'
    assert ats_version['thresholds'] == {'human_review': 85, 'send_ready': 90, 'improvement_review': 70}
    assert ats_version['quality']['external_side_effects_allowed'] is False
    assert item['readiness']['checks']['ats_simulation_report_present'] == 'pass'
    assert item['readiness']['checks']['ats_human_review_minimum'] == 'pass'
    assert item['readiness']['checks']['ats_resume_structure'] == 'pass'
print('\nverified_ats_reports', len(payload['results']))
