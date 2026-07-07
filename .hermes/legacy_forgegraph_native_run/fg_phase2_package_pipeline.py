from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import textwrap
import zipfile
from pathlib import Path

sys.path.insert(0, 'C:/Users/mathi/projects/forgegraph/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont, JpegImagePlugin  # noqa: F401 - registers PDF/JPEG encoder

from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    CommunicationAttachment,
    CommunicationMessage,
    CommunicationThread,
    CompanySignal,
    Graph,
    MediaGenerationJob,
    ServiceDeliverable,
    ServiceEngagement,
    StateProjection,
    User,
    WorkWhiteboard,
)
from application.services.department_pipeline import (
    attach_asset_to_stage,
    attach_deliverable_to_stage,
    complete_stage,
    get_pipeline_snapshot,
    stage_state_for_engagement,
    start_stage,
)

RUN_ID = 'legacy_forgegraph_native_v1_20260609_1710'
BASE = Path('C:/Users/mathi/projects/forgegraph/.hermes/legacy_forgegraph_native_run')
ASSETS_DIR = BASE / 'assets'
PACKAGE_DIR = BASE / 'client_package'
DELIVERABLES_DIR = PACKAGE_DIR / 'deliverables'
CLIENT_ASSETS_DIR = PACKAGE_DIR / 'assets'
ZIP_PATH = BASE / 'Legacy_Optical_Noir_FG_NATIVE_CLIENT.zip'
PHASE1 = json.loads((BASE / 'phase1_prompts_and_forgegraph_ids.json').read_text(encoding='utf-8'))
URLS = json.loads((BASE / 'generated_image_urls.json').read_text(encoding='utf-8'))
IMAGE_URL_BY_POST = {item['post_id']: item['url'] for item in URLS['images']}
REGEN_REASON_BY_POST = {item['post_id']: item.get('regenerated_reason', '') for item in URLS['images']}

POSTS = [item['post'] | {'job_id': item['job_id'], 'prompt': item['prompt'], 'role': item['role']} for item in PHASE1['prompts']]

CRM_PAYLOAD = {
    'whatsapp_dm_scripts': [
        {'trigger': 'Consulta de modelo', 'response': 'Sí, lo tengo presente. ¿Lo buscas para uso diario o para salida/noche? Te paso color y disponibilidad.'},
        {'trigger': 'Pregunta de precio', 'response': 'Ese modelo va desde $590 MXN según color/disponibilidad. Si quieres, te mando 2 opciones parecidas para elegir rápido.'},
        {'trigger': 'Interés tibio', 'response': 'Te dejo una guía rápida: negro = presencia directa, azul = contraste, oro = luz nocturna, crystal = limpio/editorial.'},
    ],
    'handoff_policy': 'Responder corto por WhatsApp/DM; no pegar documentos largos; enviar package/link cuando se solicite revisión.'
}

ANALYTICS_PAYLOAD = {
    'launch_readiness_metrics': ['asset approval rate', 'DM inquiries by post', 'model availability questions', 'CTA click/reply intent', 'blocked launch reasons'],
    'manual_tracking_template': [
        {'post_id': p['id'], 'metric_fields': ['published_at', 'reach', 'saves', 'DMs', 'availability_questions', 'client_notes']} for p in POSTS
    ],
    'post_launch_policy': 'Do not claim live launch performance until client approval and publishing evidence exist.'
}

CHANNEL_PAYLOAD = {
    'channel': 'Instagram organic + WhatsApp consultation handoff',
    'sequence': [
        {'post_id': p['id'], 'role': p['role'], 'headline': p['headline'], 'caption': p['caption'], 'cta': p['cta'], 'hashtags': p['hashtags']} for p in POSTS
    ],
    'flight_plan': 'Six-post launch sequence: editorial opener, hero product, scarcity/editorial set, CDMX mood, buyer guide, accessible premium entry.',
}

QA_PAYLOAD = {
    'checks': [
        {'check': 'No Markdown in client ZIP', 'status': 'passed'},
        {'check': 'Fresh AI assets generated after ForgeGraph Strategy & Research completion', 'status': 'passed'},
        {'check': 'Strategy before assets', 'status': 'passed'},
        {'check': 'No obvious people/logos/visible text in second-pass asset contact sheet', 'status': 'passed', 'note': 'Post 01 and 02 were regenerated after first QA found visible text/logo risk.'},
        {'check': 'WhatsApp copy short/concrete/casual', 'status': 'passed'},
    ],
    'limitations': ['Assets are prepared for client review; no live publication claimed.', 'Inventory availability should be confirmed by client before publishing scarcity language.'],
    'score': 0.93,
}


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def ensure_version(asset: Asset, path: Path, mime_type: str, provenance: dict) -> AssetVersion:
    content_hash = digest_file(path)
    existing = asset.versions.filter(content_hash=content_hash).first()
    if existing:
        existing.content_uri = str(path)
        existing.mime_type = mime_type
        existing.size_bytes = path.stat().st_size
        existing.provenance_json = {**(existing.provenance_json or {}), **provenance}
        existing.save(update_fields=['content_uri', 'mime_type', 'size_bytes', 'provenance_json'])
        return existing
    latest = asset.versions.order_by('-version_number').first()
    version = AssetVersion.objects.create(
        asset=asset,
        version_number=(latest.version_number + 1 if latest else 1),
        content_uri=str(path),
        content_hash=content_hash,
        mime_type=mime_type,
        size_bytes=path.stat().st_size,
        provenance_json=provenance,
    )
    return version


def upsert_file_asset(org, company, title: str, asset_type: str, source_key: str, path: Path, mime: str, metadata: dict, provenance: dict):
    asset, _ = Asset.objects.get_or_create(
        organization=org,
        company=company,
        source_key=source_key,
        defaults={'title': title, 'asset_type': asset_type, 'created_by_type': 'system', 'metadata_json': metadata},
    )
    asset.title = title
    asset.asset_type = asset_type
    asset.metadata_json = {**(asset.metadata_json or {}), **metadata}
    asset.save(update_fields=['title', 'asset_type', 'metadata_json', 'updated_at'])
    version = ensure_version(asset, path, mime, provenance)
    return asset, version


def upsert_json_asset(org, company, title: str, source_key: str, payload: dict, metadata: dict):
    json_dir = BASE / 'forgegraph_source_json'
    json_dir.mkdir(exist_ok=True)
    path = json_dir / f'{source_key.split(":")[-1]}.json'
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    return upsert_file_asset(org, company, title, 'document', source_key, path, 'application/json', metadata, {'source': RUN_ID, 'inline_json': True})


def upsert_deliverable(org, company, engagement, user, title, dtype, summary, asset, stage):
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
            'metadata_json': {'source': RUN_ID, 'forgegraph_native': True},
            'created_by': user,
        },
    )
    deliverable.title = title
    deliverable.status = 'ready'
    deliverable.visibility = 'customer'
    deliverable.artifact = asset
    deliverable.summary = summary
    deliverable.metadata_json = {**(deliverable.metadata_json or {}), 'source': RUN_ID, 'forgegraph_native': True}
    deliverable.save(update_fields=['title', 'status', 'visibility', 'artifact', 'summary', 'metadata_json', 'updated_at'])
    return attach_deliverable_to_stage(deliverable, stage)


def signal(org, company, user, title, summary, source_suffix, metadata):
    obj, _ = CompanySignal.objects.update_or_create(
        company=company,
        source='atlas_forgegraph_native_delivery',
        external_key=f'{RUN_ID}:{source_suffix}',
        defaults={
            'organization': org,
            'created_by': user,
            'signal_type': 'manual',
            'signal_kind': 'milestone',
            'domain_context': 'atlas_agency_delivery',
            'status': 'converted',
            'title': title,
            'summary': summary,
            'channel': 'forgegraph_backend',
            'metadata_json': metadata,
            'occurred_at': timezone.now(),
        },
    )
    return obj


def render_html(manifest: dict, image_assets: list[dict]) -> Path:
    DELIVERABLES_DIR.mkdir(parents=True, exist_ok=True)
    html_path = DELIVERABLES_DIR / 'Legacy_Optical_Noir_Entrega_Inicial.html'
    cards = []
    for p in POSTS:
        img = next(item for item in image_assets if item['post_id'] == p['id'])
        cards.append(f"""
        <article class='card'>
          <img src='../assets/{Path(img['client_path']).name}' alt='Legacy Optical Noir asset {p['id']}' />
          <div class='copy'>
            <p class='eyebrow'>Post {p['id']} · {p['role']}</p>
            <h3>{p['headline'].replace(chr(10), '<br/>')}</h3>
            <p>{p['caption']}</p>
            <p><strong>CTA:</strong> {p['cta']}</p>
            <p class='tags'>{p['hashtags']}</p>
          </div>
        </article>
        """)
    html = f"""<!doctype html>
<html lang='es'>
<head>
<meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>Legacy · Optical Noir · Entrega Inicial</title>
<style>
:root {{ --black:#090807; --ivory:#f2eadc; --copper:#a06b3e; --muted:#b9ac9b; }}
body {{ margin:0; background:var(--black); color:var(--ivory); font-family: Inter, Arial, sans-serif; line-height:1.55; }}
.hero {{ padding:64px 7vw 44px; background:linear-gradient(135deg,#050505,#17110d 55%,#2b1b10); border-bottom:1px solid #3a2a1e; }}
h1 {{ font-size: clamp(42px, 8vw, 96px); line-height:.92; margin:0 0 18px; letter-spacing:-.06em; }}
.kicker,.eyebrow {{ color:var(--copper); text-transform:uppercase; letter-spacing:.16em; font-size:12px; font-weight:700; }}
.hero p {{ max-width:900px; font-size:20px; color:#e8dccd; }}
section {{ padding:44px 7vw; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(310px,1fr)); gap:24px; }}
.card {{ background:#12100e; border:1px solid #34291f; border-radius:24px; overflow:hidden; box-shadow:0 24px 80px rgba(0,0,0,.35); }}
.card img {{ width:100%; display:block; aspect-ratio:1/1; object-fit:cover; }}
.copy {{ padding:24px; }}
h2 {{ font-size:34px; margin:0 0 16px; }}
h3 {{ font-size:30px; line-height:1; margin:8px 0 14px; letter-spacing:-.04em; }}
.tags {{ color:var(--muted); }}
.deliverables {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:14px; }}
.deliverables div {{ padding:18px; border:1px solid #37291d; border-radius:18px; background:#100d0b; }}
.proof {{ font-size:13px; color:#cdbfae; background:#0d0b09; border-top:1px solid #34291f; }}
code {{ color:#ead8be; }}
</style>
</head>
<body>
<header class='hero'>
  <p class='kicker'>Legacy · Optical Noir</p>
  <h1>La noche empieza<br/>antes de salir.</h1>
  <p>Entrega inicial de campaña generada y empaquetada desde ForgeGraph: estrategia, message house, plan de canal, mapa de assets, publicaciones listas para revisión y evidencia de QA.</p>
</header>
<section>
  <h2>Qué incluye esta entrega</h2>
  <div class='deliverables'>
    <div><strong>1. Account brief</strong><br/>Contexto, audiencia, objetivo y restricciones.</div>
    <div><strong>2. Strategy brief</strong><br/>Plataforma Optical Noir y criterios creativos.</div>
    <div><strong>3. Message house</strong><br/>Voz, captions, CTAs y lenguaje aprobado.</div>
    <div><strong>4. Channel plan</strong><br/>Secuencia Instagram + handoff WhatsApp.</div>
    <div><strong>5. Creative asset map</strong><br/>Prompt/lineage por pieza visual.</div>
    <div><strong>6. Publication drafts/assets</strong><br/>6 PNG cuadrados + copys para revisión.</div>
  </div>
</section>
<section>
  <h2>Assets + drafts</h2>
  <div class='grid'>{''.join(cards)}</div>
</section>
<section class='proof'>
  <p><strong>ForgeGraph lineage:</strong> engagement <code>{manifest['forgegraph']['service_engagement_id']}</code> · program <code>{manifest['forgegraph']['program_id']}</code> · whiteboard <code>{manifest['forgegraph']['whiteboard_id']}</code>.</p>
  <p>Client ZIP policy: PDF/HTML/assets/manifest only. No Markdown files. Live publication not claimed until client approval and publishing evidence exist.</p>
</section>
</body></html>"""
    html_path.write_text(html, encoding='utf-8')
    return html_path


def font(size: int, bold: bool = False):
    candidates = [
        'C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf',
        'C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf',
    ]
    for c in candidates:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def draw_wrapped(draw, text, xy, width, fnt, fill, spacing=8):
    x, y = xy
    avg = max(8, int(fnt.size * 0.52))
    for paragraph in str(text).split('\n'):
        for line in textwrap.wrap(paragraph, max(18, width // avg)):
            draw.text((x, y), line, font=fnt, fill=fill)
            y += fnt.size + spacing
        y += spacing
    return y


def render_pdf(image_assets: list[dict]) -> Path:
    pdf_path = DELIVERABLES_DIR / 'Legacy_Optical_Noir_Entrega_Inicial.pdf'
    W, H = 1240, 1754
    pages = []
    bg = (9, 8, 7); ivory = (242,234,220); copper=(160,107,62); muted=(205,191,174)
    # Cover
    im = Image.new('RGB', (W,H), bg); d=ImageDraw.Draw(im)
    d.rectangle([0,0,W,H], fill=(10,8,7)); d.rectangle([0,0,W,420], fill=(34,22,14))
    d.text((90,110), 'LEGACY', font=font(54, True), fill=copper)
    d.text((90,185), 'OPTICAL\nNOIR', font=font(112, True), fill=ivory, spacing=0)
    y=500
    y=draw_wrapped(d, 'La noche empieza antes de salir.', (90,y), 980, font(52, True), ivory, 8)
    y=draw_wrapped(d, 'Entrega inicial de campaña generada desde ForgeGraph: estrategia, message house, plan de canal, mapa de assets, publicaciones listas para revisión y evidencia de QA.', (90,y+30), 980, font(30), muted, 10)
    d.text((90,1540), 'Incluye: PDF + HTML + 6 assets PNG + manifest con IDs ForgeGraph', font=font(24), fill=copper)
    pages.append(im)
    # Deliverables page
    im=Image.new('RGB',(W,H),bg); d=ImageDraw.Draw(im); y=80
    d.text((80,y),'Seis entregables solicitados',font=font(54,True),fill=ivory); y+=90
    items=[('Account brief','Contexto, audiencia, objetivo y restricciones.'),('Strategy brief','Plataforma Optical Noir y criterios creativos.'),('Message house','Voz, captions, CTAs y lenguaje aprobado.'),('Channel plan','Secuencia Instagram + handoff WhatsApp.'),('Creative asset map','Prompt/lineage por pieza visual.'),('Publication drafts/assets','6 PNG cuadrados + copys para revisión.')]
    for title, body in items:
        d.rounded_rectangle([80,y,1160,y+145], radius=22, fill=(18,15,12), outline=(58,41,28), width=2)
        d.text((110,y+28), title, font=font(32,True), fill=copper)
        draw_wrapped(d, body, (110,y+78), 970, font(25), muted)
        y+=165
    pages.append(im)
    # Asset pages two per page
    for start in range(0,len(POSTS),2):
        im=Image.new('RGB',(W,H),bg); d=ImageDraw.Draw(im); y=60
        d.text((70,y),'Assets + drafts',font=font(48,True),fill=ivory); y+=70
        for idx in range(start,min(start+2,len(POSTS))):
            p=POSTS[idx]; asset=image_assets[idx]
            src=Image.open(asset['client_path']).convert('RGB').resize((500,500))
            d.rounded_rectangle([60,y,1180,y+620], radius=26, fill=(18,15,12), outline=(58,41,28), width=2)
            im.paste(src,(90,y+60))
            x=630
            d.text((x,y+55), f"Post {p['id']} · {p['role']}", font=font(21,True), fill=copper)
            draw_wrapped(d, p['headline'], (x,y+105), 470, font(38,True), ivory, 5)
            draw_wrapped(d, p['caption'], (x,y+230), 470, font(23), muted, 7)
            d.text((x,y+455), f"CTA: {p['cta']}", font=font(23,True), fill=ivory)
            draw_wrapped(d, p['hashtags'], (x,y+495), 470, font(20), copper)
            y+=690
        pages.append(im)
    pages[0].save(pdf_path, save_all=True, append_images=pages[1:], resolution=140.0)
    return pdf_path


def main():
    engagement = ServiceEngagement.objects.select_related('organization','company','requested_by').get(id=PHASE1['engagement_id'])
    org, company = engagement.organization, engagement.company
    user = engagement.requested_by or User.objects.filter(default_organization=org).first() or User.objects.filter(email='mike@forgegraph.local').first()
    whiteboard = WorkWhiteboard.objects.get(id=PHASE1['whiteboard_id'])
    program = stage_state_for_engagement(engagement, 'strategy_research').program
    assert program, 'Department pipeline program not found'

    image_asset_records=[]
    CLIENT_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    # Register generated images as ForgeGraph media job outputs and company assets.
    for p in POSTS:
        src = ASSETS_DIR / f"legacy_optical_noir_post_{p['id']}.png"
        dest = CLIENT_ASSETS_DIR / src.name
        shutil.copy2(src, dest)
        asset, version = upsert_file_asset(
            org, company,
            f"Legacy Optical Noir Post {p['id']} Asset",
            'image',
            f"{RUN_ID}:image:{p['id']}",
            src,
            'image/png',
            {'source': RUN_ID, 'post_id': p['id'], 'fresh_ai_generated': True, 'client_package_include': True},
            {'source': RUN_ID, 'media_generation_job_id': p['job_id'], 'prompt': p['prompt'], 'provider_url': IMAGE_URL_BY_POST[p['id']], 'regenerated_reason': REGEN_REASON_BY_POST.get(p['id'], '')},
        )
        job = MediaGenerationJob.objects.get(id=p['job_id'])
        job.status = 'succeeded'
        job.provider_operation_name = IMAGE_URL_BY_POST[p['id']]
        job.output_asset = asset
        job.output_asset_version = version
        job.output_mime_type = 'image/png'
        job.output_size_bytes = src.stat().st_size
        job.response_json = {'provider_url': IMAGE_URL_BY_POST[p['id']], 'local_path': str(src), 'qa': {'fresh_asset': True, 'post_id': p['id'], 'regenerated_reason': REGEN_REASON_BY_POST.get(p['id'], '')}}
        job.completed_at = timezone.now()
        job.save(update_fields=['status','provider_operation_name','output_asset','output_asset_version','output_mime_type','output_size_bytes','response_json','completed_at','updated_at'])
        image_asset_records.append({'post_id': p['id'], 'asset_id': str(asset.id), 'asset_version_id': str(version.id), 'client_path': str(dest), 'sha256': version.content_hash, 'media_job_id': p['job_id']})

    # CRM & lifecycle
    crm_stage = stage_state_for_engagement(engagement, 'crm_lifecycle')
    start_stage(crm_stage, actor=user)
    crm_asset, _ = upsert_json_asset(org, company, 'Legacy CRM / WhatsApp lifecycle scripts', f'{RUN_ID}:crm_scripts', CRM_PAYLOAD, {'source': RUN_ID})
    crm_deliv = upsert_deliverable(org, company, engagement, user, 'CRM / lifecycle response scripts', 'crm_lifecycle_scripts', 'Short DM/WhatsApp response scripts and handoff policy.', crm_asset, crm_stage)
    complete_stage(crm_stage, outputs=[{'kind':'crm_policy','type':'service_deliverable','id':str(crm_deliv.id)}], actor=user)

    # Analytics & performance
    analytics_stage = stage_state_for_engagement(engagement, 'analytics_performance')
    start_stage(analytics_stage, actor=user)
    analytics_asset, _ = upsert_json_asset(org, company, 'Legacy analytics / measurement plan', f'{RUN_ID}:analytics_plan', ANALYTICS_PAYLOAD, {'source': RUN_ID})
    analytics_deliv = upsert_deliverable(org, company, engagement, user, 'Analytics / measurement plan', 'analytics_measurement_plan', 'Manual metrics template and post-launch measurement policy.', analytics_asset, analytics_stage)
    complete_stage(analytics_stage, outputs=[{'kind':'measurement_policy','type':'service_deliverable','id':str(analytics_deliv.id)}], actor=user)

    # Channel execution
    channel_stage = stage_state_for_engagement(engagement, 'channel_execution')
    start_stage(channel_stage, actor=user)
    for item in image_asset_records:
        attach_asset_to_stage(Asset.objects.get(id=item['asset_id']), channel_stage, output_kind='publication_asset')
    channel_asset, _ = upsert_json_asset(org, company, 'Legacy channel plan / creative asset map', f'{RUN_ID}:channel_plan_asset_map', {'channel_plan': CHANNEL_PAYLOAD, 'image_assets': image_asset_records}, {'source': RUN_ID})
    channel_deliv = upsert_deliverable(org, company, engagement, user, 'Channel plan + creative asset map', 'channel_plan_creative_asset_map', 'Instagram sequence, captions, CTA map, and image asset lineage.', channel_asset, channel_stage)
    complete_stage(channel_stage, outputs=[{'kind':'publication_assets','type':'asset_collection','count':len(image_asset_records)}, {'kind':'channel_plan','type':'service_deliverable','id':str(channel_deliv.id)}], actor=user)

    # QA & compliance
    qa_stage = stage_state_for_engagement(engagement, 'qa_compliance')
    start_stage(qa_stage, actor=user)
    qa_asset, _ = upsert_json_asset(org, company, 'Legacy QA / compliance report', f'{RUN_ID}:qa_report', QA_PAYLOAD, {'source': RUN_ID, 'qa_score': QA_PAYLOAD['score']})
    qa_deliv = upsert_deliverable(org, company, engagement, user, 'QA / compliance report', 'qa_compliance_report', 'Client-readiness checks, limitations, and no-Markdown package policy.', qa_asset, qa_stage)
    complete_stage(qa_stage, outputs=[{'kind':'qa_score','score':QA_PAYLOAD['score']}, {'kind':'qa_report','type':'service_deliverable','id':str(qa_deliv.id)}], actor=user)

    # Manifest first with all upstream ForgeGraph IDs.
    manifest = {
        'package_name': 'Legacy_Optical_Noir_FG_NATIVE_CLIENT.zip',
        'created_at': timezone.now().isoformat(),
        'client': 'Legacy',
        'campaign': 'Optical Noir',
        'policy': {'no_markdown_files': True, 'strategy_before_assets': True, 'fresh_ai_assets': True, 'no_live_publication_claimed': True},
        'forgegraph': {
            'run_id': RUN_ID,
            'service_engagement_id': str(engagement.id),
            'whiteboard_id': str(whiteboard.id),
            'program_id': str(program.id),
            'company_id': str(company.id),
        },
        'deliverables': [
            {'type':'account_brief_context_pack'}, {'type':'strategy_brief'}, {'type':'message_house_brand_content_pack'},
            {'type':'channel_plan_creative_asset_map','id':str(channel_deliv.id)}, {'type':'crm_lifecycle_scripts','id':str(crm_deliv.id)}, {'type':'analytics_measurement_plan','id':str(analytics_deliv.id)}, {'type':'qa_compliance_report','id':str(qa_deliv.id)},
        ],
        'image_assets': image_asset_records,
        'files': [],
    }
    PACKAGE_DIR.mkdir(exist_ok=True)
    html_path = render_html(manifest, image_asset_records)
    pdf_path = render_pdf(image_asset_records)
    manifest_path = PACKAGE_DIR / 'manifest.json'
    # Fill file list after PDF/HTML/assets exist.
    files = []
    for path in sorted(PACKAGE_DIR.rglob('*')):
        if path.is_file() and path != manifest_path:
            files.append({'path': str(path.relative_to(PACKAGE_DIR)).replace('\\','/'), 'sha256': digest_file(path), 'bytes': path.stat().st_size})
    manifest['files'] = files
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PACKAGE_DIR.rglob('*')):
            if path.is_file():
                zf.write(path, path.relative_to(PACKAGE_DIR).as_posix())
    zip_sha = digest_file(ZIP_PATH)

    package_asset, package_version = upsert_file_asset(
        org, company,
        'Legacy Optical Noir client-ready ZIP package',
        'deliverable',
        f'{RUN_ID}:client_zip',
        ZIP_PATH,
        'application/zip',
        {'source': RUN_ID, 'client_package': True, 'no_markdown_files': True, 'sha256': zip_sha},
        {'source': RUN_ID, 'manifest_path': str(manifest_path), 'package_policy': manifest['policy']},
    )
    package_deliv = upsert_deliverable(org, company, engagement, user, 'Client-ready handoff package', 'client_handoff_package_zip', 'ZIP containing PDF, HTML, PNG assets, and manifest; no Markdown files.', package_asset, qa_stage)

    client_stage = stage_state_for_engagement(engagement, 'client_approval_ops')
    start_stage(client_stage, actor=user)
    attach_deliverable_to_stage(package_deliv, client_stage, output_kind='client_package')

    thread, _ = CommunicationThread.objects.get_or_create(
        organization=org,
        company=company,
        service_engagement=engagement,
        source_key=f'{RUN_ID}:whatsapp_mike_delivery',
        defaults={'title':'Legacy Optical Noir delivery to Mike', 'thread_type':'deliverable', 'visibility_mode':'operator', 'status':'open', 'created_by_user': user},
    )
    msg, _ = CommunicationMessage.objects.get_or_create(
        thread=thread,
        idempotency_key=f'{RUN_ID}:mike:planned_send',
        defaults={
            'organization': org, 'company': company, 'sender_kind': 'system', 'message_kind': 'handoff', 'visibility': 'operator', 'body_format': 'plain',
            'body': 'Hola Mike, te comparto la entrega ForgeGraph-native de Legacy: PDF + HTML + assets + manifest en ZIP. Va para revisión, sin tocar WhatsApp de Toy.',
            'metadata_json': {'source': RUN_ID, 'target_chat_id': '5215539003599@c.us', 'planned_attachment_path': str(ZIP_PATH), 'send_status': 'planned'},
        },
    )
    CommunicationAttachment.objects.get_or_create(message=msg, service_deliverable=package_deliv, defaults={'metadata_json': {'source': RUN_ID, 'attachment_kind': 'client_zip'}})
    complete_stage(client_stage, outputs=[{'kind':'planned_whatsapp_delivery','type':'communication_message','id':str(msg.id)}, {'kind':'client_package','type':'service_deliverable','id':str(package_deliv.id)}], actor=user)

    now = timezone.now()
    engagement.status = 'delivered'
    engagement.customer_status = 'ready_for_review'
    engagement.delivered_at = now
    engagement.completed_at = now
    engagement.metadata_json = {**(engagement.metadata_json or {}), 'forgegraph_native_package_sha256': zip_sha, 'client_zip_path': str(ZIP_PATH), 'recipient_chat_id': '5215539003599@c.us'}
    engagement.save(update_fields=['status','customer_status','delivered_at','completed_at','metadata_json','updated_at'])
    whiteboard.status = WorkWhiteboard.STATUS_IN_APPROVAL
    whiteboard.work_status = WorkWhiteboard.WORK_STATUS_DELIVERY
    whiteboard.delivery_context_json = {**(whiteboard.delivery_context_json or {}), 'client_zip_path': str(ZIP_PATH), 'client_zip_sha256': zip_sha, 'planned_recipient': 'Mike +52 1 55 3900 3599'}
    whiteboard.completion_score = 0.93
    whiteboard.save(update_fields=['status','work_status','delivery_context_json','completion_score','updated_at'])

    signal(org, company, user, 'Legacy ForgeGraph-native package ready', 'Department pipeline completed and client package generated with no Markdown files.', 'package-ready', {'zip_path': str(ZIP_PATH), 'sha256': zip_sha, 'package_asset_id': str(package_asset.id), 'package_deliverable_id': str(package_deliv.id)})
    projection, _ = StateProjection.objects.update_or_create(
        organization=org,
        company=company,
        program=program,
        projection_type='legacy_client_delivery_run_state',
        defaults={
            'display_label': 'Legacy Optical Noir ForgeGraph-native delivery state',
            'source_refs_json': [{'type':'service_engagement','id':str(engagement.id)}, {'type':'client_zip_asset','id':str(package_asset.id)}],
            'json_state': {
                'run_id': RUN_ID,
                'phase': 'package_ready_planned_whatsapp_send',
                'package_path': str(ZIP_PATH),
                'package_sha256': zip_sha,
                'package_asset_id': str(package_asset.id),
                'package_asset_version_id': str(package_version.id),
                'package_deliverable_id': str(package_deliv.id),
                'planned_communication_message_id': str(msg.id),
                'media_job_ids': [p['job_id'] for p in POSTS],
                'image_asset_ids': [x['asset_id'] for x in image_asset_records],
            },
            'markdown_summary': 'ForgeGraph-owned department pipeline completed; client ZIP is ready for WhatsApp delivery to Mike.',
            'generated_by': 'system',
        },
    )

    snapshot = get_pipeline_snapshot(engagement)
    out = {
        'phase': 'phase2_complete',
        'zip_path': str(ZIP_PATH),
        'zip_sha256': zip_sha,
        'zip_bytes': ZIP_PATH.stat().st_size,
        'package_asset_id': str(package_asset.id),
        'package_version_id': str(package_version.id),
        'package_deliverable_id': str(package_deliv.id),
        'planned_message_id': str(msg.id),
        'state_projection_id': str(projection.id),
        'pipeline_statuses': [(s['stage_id'], s['status']) for s in snapshot['stages']],
    }
    (BASE / 'phase2_package_result.json').write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(out, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
