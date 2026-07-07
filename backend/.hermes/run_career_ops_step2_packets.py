import io
import json
from pathlib import Path

from django.core.management import call_command
from infrastructure.orm.models import Asset, CompanyOpportunity, Graph

COMPANY_ID = 'f950d3ae-ca93-41a3-9d00-0ca3e12e3f50'
OUTPUT_PATH = Path('/app/.hermes/career_ops_step2_packets_20260617.json')
company = Graph.objects.get(id=COMPANY_ID)
cv_text = Path('/app/.hermes/miguel-athie-cv.txt').read_text(encoding='utf-8')
summary = 'Backend-leaning Software Engineer building production APIs, data systems, and AI-native workflows.'
proof_points = [
    'Built backend APIs and data systems using Python, FastAPI, Django, PostgreSQL, Redis, and Celery.',
    'Built AI-native workflows including RAG, LangGraph-style agentic workflows, and production automation.',
    'Worked across observability, tests, Prometheus, React, Next.js, and TypeScript for production software delivery.',
    'Has Mexican and Spanish citizenship, with work eligibility for Mexico, Spain, and the European Union.',
]
asset, _ = Asset.objects.get_or_create(
    organization=company.organization,
    company=company,
    source_key='career_ops:cv_source',
    defaults={
        'title': 'Miguel Athie Base CV',
        'asset_type': 'document',
        'created_by_type': 'system',
        'metadata_json': {},
    },
)
asset.title = 'Miguel Athie Base CV'
asset.asset_type = 'document'
asset.status = 'active'
asset.metadata_json = {
    'summary': summary,
    'proof_points': proof_points,
    'full_text': cv_text,
    'career_ops': {
        'deliverable_type': 'cv_source',
        'source': 'miguel-athie-cv.txt',
        'external_side_effects_allowed': False,
    },
}
asset.save()

results = []
for index, opportunity in enumerate(CompanyOpportunity.objects.filter(company=company).order_by('created_at'), start=1):
    out = io.StringIO()
    call_command(
        'build_career_ops_application_packet',
        company_id=str(company.id),
        user_id=str(company.owner_id),
        opportunity_id=str(opportunity.id),
        idempotency_key=f'career-ops-step2:{company.id}:{opportunity.id}:20260617:{index}',
        stdout=out,
    )
    payload = json.loads(out.getvalue())
    payload['opportunity_title'] = opportunity.title
    payload['employer_name'] = (opportunity.metadata_json or {}).get('career_ops', {}).get('employer_name')
    results.append(payload)

OUTPUT_PATH.write_text(json.dumps({'company_id': str(company.id), 'base_cv_asset_id': str(asset.id), 'results': results}, indent=2, sort_keys=True), encoding='utf-8')
print(json.dumps({'company_id': str(company.id), 'base_cv_asset_id': str(asset.id), 'result_count': len(results), 'output_path': str(OUTPUT_PATH)}, sort_keys=True))
for item in results:
    print(item['opportunity_title'], item['packet_asset_version_id'], item['tailored_resume_asset_version_id'], item['cover_letter_asset_version_id'], item['readiness']['status'], item['readiness']['checks'])
