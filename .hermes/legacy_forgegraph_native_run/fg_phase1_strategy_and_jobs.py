from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone as dt_timezone

sys.path.insert(0, 'C:/Users/mathi/projects/forgegraph/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from django.utils import timezone
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    DepartmentRegistry,
    Graph,
    Organization,
    OrganizationMembership,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    User,
    WorkWhiteboard,
    MediaGenerationJob,
    StateProjection,
)
from application.services.department_pipeline import (
    attach_deliverable_to_stage,
    complete_stage,
    create_pipeline_for_engagement,
    get_pipeline_snapshot,
    stage_state_for_engagement,
    start_stage,
)

RUN_ID = 'legacy_forgegraph_native_v1_20260609_1710'
RUN_DIR = Path('C:/Users/mathi/projects/forgegraph/.hermes/legacy_forgegraph_native_run')
RUN_DIR.mkdir(parents=True, exist_ok=True)

DEPARTMENTS = [
    ('strategy_research', 'Strategy & Research'),
    ('brand_content', 'Brand & Content'),
    ('crm_lifecycle', 'CRM & Lifecycle'),
    ('analytics_performance', 'Analytics & Performance'),
    ('channel_execution', 'Channel Execution'),
    ('qa_compliance', 'QA & Compliance'),
    ('client_approval_ops', 'Client / Approval Ops'),
]

POSTS = [
    {'id':'01','role':'Brand launch / editorial','headline':'La noche empieza\nantes de salir.','caption':'La noche empieza antes de salir. Legacy reúne siluetas importadas, presencia medida y entrega directa en CDMX. Explora modelos desde $590 MXN.','cta':'Elegir mi Legacy','hashtags':'#LegacyCDMX #OpticalNoir #LentesDeSol'},
    {'id':'02','role':'MONROE / BLACK hero','headline':'Negro limpio.\nPresencia inmediata.','caption':'MONROE en negro: una silueta limpia para entrar sin explicar demasiado. Disponible en Legacy.','cta':'Apartar para la noche','hashtags':'#LegacyMonroe #LentesCDMX'},
    {'id':'03','role':'Limited-feel product set','headline':'Pocas piezas.\nMucha presencia.','caption':'Las piezas con más carácter no se quedan esperando. Hendrix, Gaga y Winehouse están en pocas piezas. Consulta color y disponibilidad.','cta':'Consultar disponibilidad','hashtags':'#LegacyDrop #CDMXStyle'},
    {'id':'04','role':'CDMX editorial archive','headline':'CDMX privada.','caption':'No es solo el modelo: es la forma de entrar. Legacy trabaja con una estética Optical Noir: negro, marfil, geometría y noche de CDMX.','cta':'Ver novedades','hashtags':'#OpticalNoir #LegacyCDMX'},
    {'id':'05','role':'Buyer guide','headline':'Elige por actitud,\nno por tendencia.','caption':'Guía rápida Legacy: azul para contraste, negro para presencia directa, oro para luz nocturna, crystal para precisión. El modelo correcto se nota antes de hablar.','cta':'Explorar modelos','hashtags':'#GuiaLegacy #SunglassesMX'},
    {'id':'06','role':'Accessible premium entry','headline':'Desde $590 MXN.','caption':'Entrar al universo Legacy no tiene que esperar. Modelos seleccionados desde $590 MXN, con entrega coordinada desde CDMX.','cta':'Entrar a promos','hashtags':'#LegacyPromo #LentesImportados'},
]

STRATEGY = {
  'client': 'Legacy',
  'campaign': 'Optical Noir',
  'objective': 'Launch a premium-feeling social sequence for Legacy that makes sunglasses feel like a CDMX editorial identity, then converts visual interest into DM/WhatsApp consultation.',
  'thesis': 'Legacy should not look like a product catalog. The campaign should feel like an Optical Noir editorial: black, ivory, copper, reflections, after-dark city energy, controlled luxury, and product-first composition.',
  'message_platform': 'La noche empieza antes de salir.',
  'audience': [
      'Style-conscious CDMX buyers looking for distinctive sunglasses without generic catalog language.',
      'Gift buyers who need a polished, easy-to-understand product choice.',
      'Night-out / editorial-style consumers who buy attitude and presence as much as the product.'
  ],
  'voice': ['Spanish-first', 'short lines', 'confident', 'editorial', 'not hype-driven', 'not discount-led'],
  'visual_constraints': {
      'mood': 'premium nocturnal CDMX editorial product photography',
      'palette': ['deep black', 'warm ivory', 'aged copper', 'subtle bottle green lens reflections'],
      'lighting': 'low-key studio lighting, soft specular highlights, reflective glass, dramatic shadow falloff',
      'composition': 'sunglasses as hero object, clean negative space, mobile-first square crop, no clutter',
      'avoid': ['generic ecommerce catalog look', 'recycled/stock-photo feel', 'busy backgrounds', 'neon party cliché', 'text baked into the image unless intentionally minimal']
  },
  'asset_generation_policy': 'Generate fresh AI assets only after this Strategy & Research stage has completed and after Brand & Content writes creative prompts.',
}

def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def ensure_base():
    user, _ = User.objects.get_or_create(email='mike@forgegraph.local', defaults={'is_active': True})
    org, _ = Organization.objects.get_or_create(name='ForgeGraph Local Agency')
    if user.default_organization_id != org.id:
        user.default_organization = org
        user.save(update_fields=['default_organization'])
    OrganizationMembership.objects.get_or_create(organization=org, user=user, defaults={'role': 'owner', 'is_default': True})
    company, _ = Graph.objects.get_or_create(
        owner=user,
        organization=org,
        external_source='atlas',
        external_ref='legacy-optical-noir',
        defaults={'name': 'Legacy', 'description': 'Legacy CDMX sunglasses agency client.'},
    )
    for slug, name in DEPARTMENTS:
        DepartmentRegistry.objects.get_or_create(
            organization=org,
            slug=slug,
            defaults={
                'name': name,
                'department_type': 'agency_department',
                'lead_user': user,
                'service_tags_json': ['atlas', 'legacy', 'digital_marketing_pro'],
                'active': True,
                'metadata_json': {'source': RUN_ID},
            },
        )
    catalog, _ = ServiceCatalogItem.objects.get_or_create(
        organization=org,
        slug='legacy-optical-noir-client-delivery',
        defaults={
            'title': 'Legacy Optical Noir Client Delivery',
            'description': 'ForgeGraph-native agency delivery run for Legacy Optical Noir.',
            'status': 'active',
            'visibility': 'customer',
            'audience': 'digital_marketing_client',
            'required_pack_ids_json': ['digital_marketing_pro.v1'],
            'metadata_json': {'source': RUN_ID},
            'created_by': user,
        },
    )
    engagement, _ = ServiceEngagement.objects.get_or_create(
        company=company,
        source_key=RUN_ID,
        defaults={
            'organization': org,
            'catalog_item': catalog,
            'status': 'in_progress',
            'customer_status': 'working',
            'public_summary': 'Legacy Optical Noir initial campaign package: six requested deliverables, PDF/HTML/assets, no Markdown to client.',
            'required_pack_ids_json': ['digital_marketing_pro.v1'],
            'intake_data_json': {'requested_deliverables': ['account_brief', 'strategy_brief', 'message_house', 'channel_plan', 'creative_asset_map', 'publication_ready_drafts_assets']},
            'metadata_json': {'source': RUN_ID, 'quality_bar': 'client_ready_pdf_assets_no_markdown'},
            'requested_by': user,
            'started_at': timezone.now(),
        },
    )
    whiteboard, _ = WorkWhiteboard.objects.get_or_create(
        organization=org,
        company=company,
        service_engagement=engagement,
        project_name='Legacy Optical Noir ForgeGraph-native delivery',
        defaults={
            'status': WorkWhiteboard.STATUS_IN_STRATEGY,
            'work_status': WorkWhiteboard.WORK_STATUS_IN_PROGRESS,
            'request_type': 'agency_client_delivery',
            'client_name': 'Legacy',
            'request_summary': 'Produce the six initial Legacy campaign deliverables through ForgeGraph department stages.',
            'objective': STRATEGY['objective'],
            'constraints_json': {'no_markdown_client_delivery': True, 'whatsapp_brief': True, 'assets_after_strategy': True},
        },
    )
    program = create_pipeline_for_engagement(engagement, created_by=user, run_context={'source': RUN_ID})
    return user, org, company, engagement, whiteboard, program

def create_text_asset(org, company, title, asset_type, source_key, payload, mime='application/json'):
    asset, _ = Asset.objects.get_or_create(
        organization=org,
        company=company,
        source_key=source_key,
        defaults={'title': title, 'asset_type': asset_type, 'created_by_type': 'system', 'metadata_json': {'source': RUN_ID}},
    )
    if not _:
        asset.title = title
        asset.asset_type = asset_type
        asset.metadata_json = {**(asset.metadata_json or {}), 'source': RUN_ID}
        asset.save(update_fields=['title', 'asset_type', 'metadata_json', 'updated_at'])
    data = json.dumps(payload, indent=2, ensure_ascii=False).encode('utf-8')
    h = sha_bytes(data)
    version, created = AssetVersion.objects.get_or_create(
        asset=asset,
        content_hash=h,
        defaults={
            'version_number': (asset.versions.count() + 1),
            'content_uri': f'forgegraph://legacy-native/{RUN_ID}/{source_key}',
            'mime_type': mime,
            'size_bytes': len(data),
            'provenance_json': {'source': RUN_ID, 'inline_content': payload},
        },
    )
    return asset, version

def create_deliverable(org, company, engagement, user, title, dtype, summary, asset, stage):
    deliverable, _ = ServiceDeliverable.objects.get_or_create(
        engagement=engagement,
        deliverable_type=dtype,
        defaults={
            'organization': org,
            'company': company,
            'title': title,
            'status': 'ready',
            'visibility': 'customer',
            'artifact': asset,
            'summary': summary,
            'metadata_json': {'source': RUN_ID, 'deliverable_type': dtype, 'format_policy': 'render_to_pdf_html_for_client'},
            'created_by': user,
        },
    )
    if not _:
        deliverable.title = title
        deliverable.status = 'ready'
        deliverable.visibility = 'customer'
        deliverable.artifact = asset
        deliverable.summary = summary
        deliverable.metadata_json = {**(deliverable.metadata_json or {}), 'source': RUN_ID, 'format_policy': 'render_to_pdf_html_for_client'}
        deliverable.save(update_fields=['title','status','visibility','artifact','summary','metadata_json','updated_at'])
    return attach_deliverable_to_stage(deliverable, stage)

def main():
    user, org, company, engagement, whiteboard, program = ensure_base()
    strategy_stage = stage_state_for_engagement(engagement, 'strategy_research')
    start_stage(strategy_stage, actor=user)
    account_payload = {
        'client': 'Legacy',
        'market': 'CDMX',
        'context': 'Sunglasses brand moving from catalog/product listing into a distinctive editorial campaign world.',
        'audience': STRATEGY['audience'],
        'constraints': {'no_markdown_client_delivery': True, 'assets_after_strategy': True},
    }
    account_asset, _ = create_text_asset(org, company, 'Legacy Account Brief / Context Pack', 'document', f'{RUN_ID}:account_brief', account_payload)
    strategy_asset, _ = create_text_asset(org, company, 'Legacy Optical Noir Strategy Constraints', 'document', f'{RUN_ID}:strategy_constraints', STRATEGY)
    d1 = create_deliverable(org, company, engagement, user, 'Account brief / context pack', 'account_brief_context_pack', 'Client context, audience, scope, and campaign constraints.', account_asset, strategy_stage)
    d2 = create_deliverable(org, company, engagement, user, 'Strategy brief', 'strategy_brief', 'Optical Noir strategy, objective, message platform, and creative constraints.', strategy_asset, strategy_stage)
    complete_stage(strategy_stage, outputs=[{'kind':'strategy_constraints','type':'asset_version','id':str(strategy_asset.id), 'policy':'assets_after_strategy'}], actor=user)

    brand_stage = stage_state_for_engagement(engagement, 'brand_content')
    start_stage(brand_stage, actor=user)
    prompts=[]
    base = 'Premium editorial product photography for a luxury-accessible sunglasses brand named Legacy, campaign concept Optical Noir. Deep black, warm ivory, aged copper, subtle green lens reflections, cinematic low-key lighting, CDMX after-dark mood, mobile-first square crop, no visible text, no logos, no people, no stock-photo feel.'
    variants = [
        'Hero sunglasses on dark smoked glass with elegant negative space for headline overlay.',
        'Black sunglasses on warm ivory stone and black lacquer surface, refined product-first composition.',
        'Three curated sunglasses silhouettes arranged like a limited archive, dramatic shadows.',
        'Sunglasses near rain-streaked window with warm CDMX city bokeh outside, quiet luxury.',
        'Four sunglasses with varied lens tones arranged as a buyer guide, modular composition.',
        'Gold-framed sunglasses on warm ivory backdrop with black vertical panel, accessible premium feeling.',
    ]
    for post, variant in zip(POSTS, variants):
        prompt = f'{base} {variant}'
        prompts.append({'post_id': post['id'], 'role': post['role'], 'prompt': prompt, 'post': post})
    message_house = {
        'voice': ['directa', 'visual', 'premium pero fácil de responder', 'sin urgencia falsa'],
        'message_platform': STRATEGY['message_platform'],
        'approved_language': ['Presencia inmediata', 'Consulta color y disponibilidad', 'El modelo correcto se nota antes de hablar'],
        'avoid': ['hype', 'descuento agresivo', 'claims absolutos'],
        'posts': POSTS,
        'creative_prompts': prompts,
    }
    brand_asset, _ = create_text_asset(org, company, 'Legacy Message House / Brand Content Pack', 'document', f'{RUN_ID}:message_house', message_house)
    d3 = create_deliverable(org, company, engagement, user, 'Message house / brand-content pack', 'message_house_brand_content_pack', 'Brand voice, caption system, post sequence, and generated media prompts.', brand_asset, brand_stage)

    jobs=[]
    for prompt in prompts:
        prompt_hash = hashlib.sha256(prompt['prompt'].encode('utf-8')).hexdigest()
        job, _ = MediaGenerationJob.objects.get_or_create(
            organization=org,
            company=company,
            idempotency_key=f'{RUN_ID}:post:{prompt["post_id"]}',
            defaults={
                'requested_by': user,
                'modality': 'image',
                'provider': 'fal_operator',
                'model': 'nous-managed-image-generation',
                'prompt': prompt['prompt'],
                'prompt_hash': prompt_hash,
                'status': 'pending',
                'request_json': {
                    'source': RUN_ID,
                    'post_id': prompt['post_id'],
                    'strategy_stage_completed_at': strategy_stage.completed_at.isoformat() if strategy_stage.completed_at else None,
                    'brand_stage_id': str(brand_stage.id),
                    'strategy_hash': hashlib.sha256(json.dumps(STRATEGY, sort_keys=True).encode()).hexdigest(),
                    'dimensions': [1080,1080],
                },
            },
        )
        jobs.append({'job_id': str(job.id), **prompt})
    complete_stage(brand_stage, outputs=[{'kind':'media_generation_jobs','count':len(jobs), 'policy':'prompts_after_strategy'}], actor=user)

    StateProjection.objects.update_or_create(
        organization=org,
        company=company,
        program=program,
        projection_type='legacy_client_delivery_run_state',
        defaults={
            'display_label': 'Legacy Optical Noir ForgeGraph-native delivery state',
            'source_refs_json': [{'type':'service_engagement','id':str(engagement.id)}, {'type':'program','id':str(program.id)}],
            'json_state': {
                'run_id': RUN_ID,
                'phase': 'strategy_brand_complete_media_jobs_pending',
                'strategy_stage_id': str(strategy_stage.id),
                'brand_stage_id': str(brand_stage.id),
                'media_job_ids': [j['job_id'] for j in jobs],
                'deliverable_ids': [str(d1.id), str(d2.id), str(d3.id)],
            },
            'markdown_summary': 'Strategy and Brand stages completed before media generation jobs were created.',
            'generated_by': 'system',
        },
    )
    out = {
        'run_id': RUN_ID,
        'engagement_id': str(engagement.id),
        'whiteboard_id': str(whiteboard.id),
        'program_id': str(program.id),
        'strategy_completed_at': strategy_stage.completed_at.isoformat() if strategy_stage.completed_at else None,
        'brand_completed_at': brand_stage.completed_at.isoformat() if brand_stage.completed_at else None,
        'prompts': jobs,
        'pipeline_snapshot': get_pipeline_snapshot(engagement),
    }
    path = RUN_DIR / 'phase1_prompts_and_forgegraph_ids.json'
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'phase':'phase1_complete', 'path': str(path), 'engagement_id': str(engagement.id), 'program_id': str(program.id), 'media_jobs': len(jobs)}, indent=2))

if __name__ == '__main__':
    main()
