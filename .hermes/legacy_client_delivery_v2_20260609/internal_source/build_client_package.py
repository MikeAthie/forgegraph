from pathlib import Path
import json, urllib.request, html
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont

run_dir = Path('C:/Users/mathi/projects/forgegraph/.hermes/legacy_client_delivery_v2_20260609')
asset_dir = run_dir / 'assets'
deliv_dir = run_dir / 'deliverables'
source_dir = run_dir / 'internal_source'
for d in [asset_dir, deliv_dir, source_dir]:
    d.mkdir(parents=True, exist_ok=True)

image_urls = [
  'https://v3b.fal.media/files/b/0a9da764/VSBsV2cx7IS8JcVX6MYDC_bUWfkJk7.png',
  'https://v3b.fal.media/files/b/0a9da765/Y7LUOpFhjdlBL-19vTPdG_Gx0o3iEM.png',
  'https://v3b.fal.media/files/b/0a9da766/amzOLiKkY2YNfw14CxWRp_WbcduRa3.png',
  'https://v3b.fal.media/files/b/0a9da767/Um5XNp9DprMwIwGkGZ2rj_ySzcP5U1.png',
  'https://v3b.fal.media/files/b/0a9da768/Ol1z71Ay5aKbfWNsVRfHg_mCxw4OtR.png',
  'https://v3b.fal.media/files/b/0a9da768/wDlDnlx10WQS6gLYDBOrK_cUMiqawj.png',
]
posts = [
  {'id':'01','role':'Brand launch / editorial','headline':'La noche empieza\nantes de salir.','caption':'La noche empieza antes de salir. Legacy reúne siluetas importadas, presencia medida y entrega directa en CDMX. Explora modelos desde $590 MXN.','cta':'Elegir mi Legacy','hashtags':'#LegacyCDMX #OpticalNoir #LentesDeSol'},
  {'id':'02','role':'MONROE / BLACK hero','headline':'Negro limpio.\nPresencia inmediata.','caption':'MONROE en negro: una silueta limpia para entrar sin explicar demasiado. Disponible en Legacy.','cta':'Apartar para la noche','hashtags':'#LegacyMonroe #LentesCDMX'},
  {'id':'03','role':'Limited-feel product set','headline':'Pocas piezas.\nMucha presencia.','caption':'Las piezas con más carácter no se quedan esperando. Hendrix, Gaga y Winehouse están en pocas piezas. Consulta color y disponibilidad.','cta':'Consultar disponibilidad','hashtags':'#LegacyDrop #CDMXStyle'},
  {'id':'04','role':'CDMX editorial archive','headline':'CDMX privada.','caption':'No es solo el modelo: es la forma de entrar. Legacy trabaja con una estética Optical Noir: negro, marfil, geometría y noche de CDMX.','cta':'Ver novedades','hashtags':'#OpticalNoir #LegacyCDMX'},
  {'id':'05','role':'Buyer guide','headline':'Elige por actitud,\nno por tendencia.','caption':'Guía rápida Legacy: azul para contraste, negro para presencia directa, oro para luz nocturna, crystal para precisión. El modelo correcto se nota antes de hablar.','cta':'Explorar modelos','hashtags':'#GuiaLegacy #SunglassesMX'},
  {'id':'06','role':'Accessible premium entry','headline':'Desde $590 MXN.','caption':'Entrar al universo Legacy no tiene que esperar. Modelos seleccionados desde $590 MXN, con entrega coordinada desde CDMX.','cta':'Entrar a promos','hashtags':'#LegacyPromo #LentesImportados'},
]

raw_paths = []
for idx, url in enumerate(image_urls, start=1):
    p = asset_dir / f'legacy_optical_noir_ai_raw_{idx:02d}.png'
    urllib.request.urlretrieve(url, p)
    raw_paths.append(p)

def font(size, bold=False, serif=False):
    choices = []
    if serif and bold:
        choices.append(Path('C:/Windows/Fonts/georgiab.ttf'))
    if serif:
        choices.append(Path('C:/Windows/Fonts/georgia.ttf'))
    if bold:
        choices.append(Path('C:/Windows/Fonts/arialbd.ttf'))
    choices.append(Path('C:/Windows/Fonts/arial.ttf'))
    for c in choices:
        if c.exists():
            return ImageFont.truetype(str(c), size)
    return ImageFont.load_default()

serif_big = font(72, serif=True)
serif_med = font(54, serif=True)
sans_small = font(22)
sans_tiny = font(18)
sans_bold = font(24, bold=True)

final_assets = []
for post, raw in zip(posts, raw_paths):
    img = Image.open(raw).convert('RGB').resize((1080, 1080), Image.LANCZOS)
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for x in range(1080):
        alpha = int(max(0, 180 * (1 - x / 680)))
        draw.line([(x, 0), (x, 1080)], fill=(0, 0, 0, alpha))
    for y in range(1080):
        alpha = int(max(0, 140 * (y - 620) / 460)) if y > 620 else 0
        draw.line([(0, y), (1080, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img.convert('RGBA'), overlay)
    draw = ImageDraw.Draw(img)
    ivory = (246, 240, 228, 255)
    copper = (199, 131, 70, 255)
    black = (5, 5, 5, 230)
    draw.text((64, 58), 'LEGACY', font=sans_bold, fill=ivory)
    draw.line((64, 94, 154, 94), fill=copper, width=3)
    draw.text((64, 104), 'OPTICAL NOIR', font=sans_tiny, fill=(230, 216, 192, 245))
    y = 720 if post['id'] in ['01', '04', '06'] else 690
    headline_font = serif_big if len(post['headline']) < 30 else serif_med
    for line in post['headline'].split('\n'):
        draw.text((64, y), line, font=headline_font, fill=ivory)
        y += headline_font.size + 4
    cta = post['cta']
    bbox = draw.textbbox((0, 0), cta, font=sans_small)
    w = bbox[2] - bbox[0]
    draw.rounded_rectangle((64, 970, 64 + w + 42, 1016), radius=23, fill=black, outline=copper, width=2)
    draw.text((85, 981), cta, font=sans_small, fill=ivory)
    final = asset_dir / f'legacy_optical_noir_post_{post["id"]}.png'
    img.convert('RGB').save(final, quality=95)
    final_assets.append(final)

sections = {
    'Account brief / context pack': 'Legacy es una marca de lentes de sol con una oportunidad clara: dejar de parecer catálogo y operar como una marca editorial con punto de vista. El territorio recomendado para esta primera salida es Optical Noir: una estética nocturna, sobria y premium que usa negro profundo, marfil cálido, cobre y reflejos de lente para convertir producto en presencia.\n\nLa audiencia principal está en CDMX y compra por actitud, regalo o salida; no solo por precio. El lenguaje debe ser español primero, breve y seguro. La venta debe sentirse como asesoría de estilo: elegir, apartar, consultar disponibilidad y explorar modelos.',
    'Strategy brief': 'Objetivo: lanzar una secuencia social que presente a Legacy como una marca con mundo propio y convierta atención visual en conversación por DM/WhatsApp.\n\nTesis: Legacy no debe competir como tienda genérica. Debe apropiarse de un look reconocible —Optical Noir— y repetirlo de forma consistente: producto protagonista, sombra dramática, ciudad nocturna, líneas cortas y claims responsables.\n\nMensaje central: “La noche empieza antes de salir.”\n\nLa campaña abre con mundo/editorial, después aterriza producto, activa urgencia controlada, refuerza estética, ayuda a elegir y cierra con una entrada accesible desde $590 MXN.',
    'Message house / brand-content pack': 'Voz: directa, visual, no ansiosa.\n\nSí decir: “Presencia inmediata”, “Consulta color y disponibilidad”, “El modelo correcto se nota antes de hablar”, “Entrar al universo Legacy no tiene que esperar”.\n\nEvitar: hype, urgencia falsa, claims absolutos o frases de descuento agresivo.\n\nSistema de caption: una frase editorial de apertura, una línea de producto o beneficio, CTA conversacional y hashtags limitados. El copy debe sonar premium pero fácil de responder.',
    'Channel plan': 'Canales de esta prueba: Instagram feed como lanzamiento visual, Instagram/Reels como pieza de movimiento posterior, WhatsApp/DM como canal conversacional y sitio/catalogo como fuente de producto/precio.\n\nCadencia sugerida: seis publicaciones en seis días. Día 1 brand launch, día 2 producto hero, día 3 pocas piezas, día 4 editorial archive, día 5 buyer guide, día 6 entrada promo.\n\nRegla operativa: si no hay conector real o aprobación final, se presenta como draft listo para revisión, no como publicación ejecutada.',
    'Creative asset map': 'Los assets fueron generados después de definir la estrategia para asegurar alineación con Optical Noir. La dirección visual usa fotografía editorial de producto, baja iluminación, fondos negros/marfil, cobre, reflejos sutiles y composición cuadrada para Instagram.\n\nCada pieza tiene un rol: apertura de mundo, hero product, sensación de pocas piezas, archivo CDMX, guía de elección y entrada accesible. Las imágenes evitan look de catálogo y dejan espacio para headline/CTA.',
    'Publication-ready drafts/assets': 'Se incluyen seis drafts cuadrados listos para revisión de feed. Cada uno tiene imagen nueva generada por IA, headline, CTA y caption sugerido. La publicación real queda sujeta a aprobación y confirmación de disponibilidad.\n\nNo se incluyen CRM, medición, QA, receipts ni performance report porque esta corrida pidió únicamente el primer paquete de entregables.'
}

section_html = ''.join(
    f"<section class='section'><h2>{html.escape(k)}</h2>" + ''.join(f"<p>{html.escape(par)}</p>" for par in v.split('\n\n')) + '</section>'
    for k, v in sections.items()
)
asset_figures = ''.join(
    f'<figure><img src="../assets/{p.name}"><figcaption>{posts[i]["id"]}. {html.escape(posts[i]["role"])} — {html.escape(posts[i]["cta"])}</figcaption></figure>'
    for i, p in enumerate(final_assets)
)
asset_table = ''.join(
    f"<tr><td>{p['id']}</td><td>{html.escape(p['role'])}</td><td><img src='../assets/{final_assets[i].name}' /></td><td><strong>{html.escape(p['headline'].replace(chr(10),' / '))}</strong><br/>{html.escape(p['caption'])}<br/><em>CTA: {html.escape(p['cta'])}</em><br/><span>{html.escape(p['hashtags'])}</span></td></tr>"
    for i, p in enumerate(posts)
)
html_doc = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Legacy — Entrega Inicial Optical Noir</title><style>
@page {{ size: A4; margin: 14mm; }}
:root{{--black:#050505;--ivory:#f6f0e4;--bone:#e6d8c0;--copper:#c78346;--green:#17382b;}}
*{{box-sizing:border-box}} body{{margin:0;background:#f7f0e6;color:#15110d;font-family:Arial,Helvetica,sans-serif;line-height:1.5}} .cover{{min-height:94vh;background:radial-gradient(circle at 75% 20%,rgba(199,131,70,.3),transparent 32%),linear-gradient(135deg,#050505,#17110d 62%,#2a170e);color:var(--ivory);padding:72px;display:flex;flex-direction:column;justify-content:center;page-break-after:always}} .kicker{{letter-spacing:.22em;text-transform:uppercase;color:var(--copper);font-size:12px}} h1{{font-family:Georgia,serif;font-size:72px;line-height:.92;margin:18px 0 22px}} .cover p{{font-size:20px;max-width:720px;color:#eadfcc}} .chips{{display:flex;gap:10px;flex-wrap:wrap;margin-top:28px}} .chips span{{border:1px solid rgba(246,240,228,.28);border-radius:999px;padding:8px 13px}} .summary{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:36px}} .card{{background:rgba(255,255,255,.06);border:1px solid rgba(246,240,228,.16);border-radius:18px;padding:18px}} .card strong{{display:block;font-size:30px;font-family:Georgia,serif}} main{{padding:0 42px 48px}} .section{{padding:32px 0;border-bottom:1px solid #ddceb8;page-break-inside:avoid}} h2{{font-family:Georgia,serif;font-size:34px;margin:0 0 16px;color:#10100d}} p{{font-size:15px;max-width:900px}} .asset-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:18px;margin-top:20px}} figure{{margin:0;background:#fffaf2;border:1px solid #dfcfb7;border-radius:16px;overflow:hidden;page-break-inside:avoid}} figure img{{width:100%;display:block}} figcaption{{padding:12px 14px;font-size:13px}} table{{width:100%;border-collapse:collapse;background:#fffaf2;border-radius:14px;overflow:hidden}} th,td{{border-bottom:1px solid #e4d6c2;padding:12px;vertical-align:top;text-align:left;font-size:13px}} th{{background:#15110d;color:#f6f0e4;text-transform:uppercase;letter-spacing:.08em;font-size:11px}} td img{{width:160px;border-radius:10px;display:block}} .note{{background:#fffaf2;border-left:5px solid var(--copper);padding:18px 20px;border-radius:0 14px 14px 0;margin:24px 0}} .footer{{padding:28px 42px;background:#050505;color:#e6d8c0;font-size:12px}}
</style></head><body><section class="cover"><div class="kicker">Legacy × Optical Noir</div><h1>Entrega Inicial<br/>de Campaña</h1><p>Brief, estrategia, message house, plan de canales, mapa creativo y drafts/assets nuevos generados con IA para revisión.</p><div class="chips"><span>Cliente: Legacy</span><span>Mercado: CDMX</span><span>Formato: PDF + assets</span><span>Estado: listo para revisión</span></div><div class="summary"><div class="card"><strong>6</strong> entregables</div><div class="card"><strong>6</strong> assets nuevos IA</div><div class="card"><strong>0</strong> Markdown para cliente</div></div></section><main>{section_html}<section class="section"><h2>Drafts visuales</h2><div class="asset-grid">{asset_figures}</div></section><section class="section"><h2>Mapa de publicación y captions</h2><table><thead><tr><th>ID</th><th>Rol</th><th>Asset</th><th>Draft copy</th></tr></thead><tbody>{asset_table}</tbody></table><div class="note"><strong>Nota de publicación:</strong> estos drafts son client-ready para revisión. Publicación real sujeta a aprobación final, confirmación de disponibilidad y conector/canal operativo.</div></section></main><div class="footer">Legacy Optical Noir · paquete generado por ForgeGraph/Hermes · entrega parcial solicitada · {datetime.now().strftime('%Y-%m-%d')}</div></body></html>'''
html_path = deliv_dir / 'Legacy_Optical_Noir_Entrega_Inicial.html'
html_path.write_text(html_doc, encoding='utf-8')

evidence = {
  'strategy_created_before_assets': True,
  'image_urls': image_urls,
  'raw_assets': [p.name for p in raw_paths],
  'final_assets': [p.name for p in final_assets],
  'client_deliverable_html': html_path.name,
  'no_markdown_in_client_zip': True,
  'created_at': datetime.now(timezone.utc).isoformat()
}
(source_dir / 'run_evidence.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps({'html_path': str(html_path), 'final_assets': [str(p) for p in final_assets], 'raw_assets': [str(p) for p in raw_paths]}, indent=2, ensure_ascii=False))
