import io
import json
from pathlib import Path

from django.core.management import call_command

from infrastructure.orm.models import Asset, CompanyOpportunity, Graph

COMPANY_ID = 'f950d3ae-ca93-41a3-9d00-0ca3e12e3f50'
OUTPUT_PATH = Path('/app/.hermes/career_ops_ats_packets_20260617.json')
company = Graph.objects.get(id=COMPANY_ID)
cv_text = Path('/app/.hermes/miguel-athie-cv.txt').read_text(encoding='utf-8')
summary = (
    'Backend-leaning Software Engineer with strong end-to-end ownership building production APIs, data systems, '
    'AI-native workflows, and async service architectures. Experienced with Python, FastAPI, PostgreSQL, Redis, '
    'workers, and Go-based backend services; comfortable taking systems from discovery and architecture through '
    'implementation, testing, observability, and launch. Strong interest in B2B/enterprise products, integrations, '
    'agentic AI, RAG, and production-grade systems that require reliability, maintainability, and operational rigor.'
)
proof_points = [
    'Built backend APIs and data systems using Python, FastAPI, Django, PostgreSQL, Redis, and Celery.',
    'Built AI-native workflows including RAG, LangGraph-style agentic workflows, and production automation.',
    'Worked across observability, tests, Prometheus, React, Next.js, and TypeScript for production software delivery.',
    'Has Mexican and Spanish citizenship, with work eligibility for Mexico and Spain.',
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
    'name': 'Miguel Athie',
    'location': 'Mexico City, MX',
    'email': 'miguel.athien@gmail.com',
    'phone': '+52 55 3900 3599',
    'github': 'GitHub: https://github.com/GreyCrossX',
    'professional_summary': summary,
    'summary': summary,
    'experience': [
        {
            'organization': 'Grey Cross Developments',
            'role': 'Product Engineer',
            'period': 'Jul 2022 – Present',
            'bullets': [
                'Owned backend products end-to-end (discovery → architecture → implementation → deployment), delivering data-driven systems for SMBs and consulting clients.',
                'Designed and implemented APIs and service boundaries with a focus on clean, maintainable interfaces and long-term iteration.',
                'Built async/event-driven pipelines for near real-time processing, improving responsiveness and reliability for data-heavy workflows.',
                'Implemented data ingestion and storage patterns using PostgreSQL and Redis/Redis Streams to handle high-volume structured data.',
                'Integrated AI-powered features into production systems, emphasizing grounded outputs and practical user workflows.',
            ],
        },
        {
            'organization': 'Vittahouse',
            'role': 'Automation & Data Consultant',
            'period': 'Oct 2019 – Nov 2025',
            'bullets': [
                'Automated accounting and audit workflows, reducing manual effort and improving consistency of recurring operational processes.',
                'Built discrepancy-detection tools to surface data issues earlier and support data-driven decision-making.',
                'Translated ambiguous stakeholder needs into shippable automation and data products, iterating based on feedback and operational constraints.',
                'Developed ingestion/normalization workflows to standardize inputs across sources and enable reliable reporting.',
            ],
        },
    ],
    'projects': [
        {
            'name': 'Lex Toolkit',
            'subtitle': 'AI agents for legal workflows (Next.js + FastAPI)',
            'period': 'Nov 2025 – Present',
            'url': 'https://github.com/MikeAthie/Lex-Toolkit',
            'bullets': [
                'Built a full-stack application with Next.js (frontend) and FastAPI (backend), designed to scale for real-world professional workflows.',
                'Developed AI agent use cases for law practice operations; the project has attracted interest from local law firms.',
                'Focused on product-quality delivery: clear API contracts, iterative UX improvements, and production-minded backend structure.',
            ],
        },
        {
            'name': 'Forgegraph',
            'subtitle': 'AI-native backend platform for agentic workflows',
            'period': '2026 – Present',
            'url': 'https://github.com/MikeAthie/ForgeGraph',
            'bullets': [
                'Built an end-to-end backend platform exploring how AI agents can interact with structured project knowledge, memory, summaries, and operational workflows.',
                'Designed and implemented backend services in Go and Django, including summarization workflows, memory lifecycle management, retry logic, safe deletion flows, dry-run execution, batching, reindexing, and admin-facing endpoints.',
                'Added production-minded reliability features, including Prometheus counters, retry mechanisms, structured service boundaries, and tests around critical workflows.',
                'Used AI-assisted development practices with rigorous validation: code review, local execution, tests, and a 4R review loop — Risk, Readability, Reliability, Resilience — to accelerate delivery without losing engineering control.',
            ],
        },
    ],
    'skills': [
        {'category': 'Backend / APIs', 'items': 'Python, FastAPI, Django, Go, REST APIs, service architecture, schema design, clean interfaces, production deployment'},
        {'category': 'Data & Async Systems', 'items': 'PostgreSQL, Redis, Redis Streams, Celery, event-driven pipelines, workers, WebSockets, batch processing'},
        {'category': 'AI Engineering', 'items': 'RAG, LangGraph, agentic workflows, AI-assisted development, LLM integration, grounded outputs, prompt/workflow design'},
        {'category': 'Reliability & Operations', 'items': 'Prometheus, observability, retries, dry-run workflows, safe deletion flows, testing, debugging, production maintenance'},
        {'category': 'Frontend / Product', 'items': 'React, Next.js, TypeScript, dashboards, internal tools, product discovery, stakeholder collaboration'},
        {'category': 'Delivery', 'items': 'end-to-end ownership, requirements shaping, technical documentation, code review, high-urgency shipping'},
    ],
    'education': [
        {
            'institution': 'Instituto Tecnológico Autónomo de México (ITAM)',
            'degree': 'BSc in Law',
            'graduation_year': '2017',
            'location': 'Mexico City, Mexico',
        },
    ],
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
        idempotency_key=f'career-ops-ats:{company.id}:{opportunity.id}:20260618:professional:{index}',
        stdout=out,
    )
    payload = json.loads(out.getvalue())
    payload['opportunity_title'] = opportunity.title
    payload['employer_name'] = (opportunity.metadata_json or {}).get('career_ops', {}).get('employer_name')
    results.append(payload)

OUTPUT_PATH.write_text(json.dumps({'company_id': str(company.id), 'base_cv_asset_id': str(asset.id), 'results': results}, indent=2, sort_keys=True), encoding='utf-8')
print(json.dumps({'company_id': str(company.id), 'base_cv_asset_id': str(asset.id), 'result_count': len(results), 'output_path': str(OUTPUT_PATH)}, sort_keys=True))
for item in results:
    print(
        item['opportunity_title'],
        'packet=', item['packet_asset_version_id'],
        'resume=', item['tailored_resume_asset_version_id'],
        'recruiter=', item.get('recruiter_evaluation_asset_version_id'),
        'cover=', item['cover_letter_asset_version_id'],
        'ats=', item['ats_simulation_asset_version_id'],
        'readiness=', item['readiness']['status'],
        'ats_checks=', {k: v for k, v in item['readiness']['checks'].items() if k.startswith('ats_')},
    )
