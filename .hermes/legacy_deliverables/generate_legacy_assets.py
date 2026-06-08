from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
import json
import subprocess

root = Path('C:/Users/mathi/projects/forgegraph/.hermes/legacy_deliverables')
media = root / 'media'
root.mkdir(parents=True, exist_ok=True)
media.mkdir(parents=True, exist_ok=True)
legacy = Path('C:/Users/mathi/projects/legacy/front')

brand = {
    'name': 'Legacy',
    'category': 'Luxury glasswear / sunglasses',
    'origin': 'Mexico City',
    'positioning': 'Optical Noir: restrained luxury, CDMX night energy, severe black/ivory contrast, editorial product photography.',
    'site_repo': str(legacy),
    'hero': 'public/editorial/legacy-crew-hero.webp',
    'colors': {'ink':'#050505','ivory':'#F6F0E4','bone':'#E6D8C0','amber':'#C78346','lens_green':'#17382B','copper':'#A65A34'},
}
products = [
    {'slug':'lennon','name':'LENNON','code':'GR-8024','color':'BLUE','price':700,'status':'Disponible','image':'public/catalog/lennon/gallery-1.webp'},
    {'slug':'monroe','name':'MONROE','code':'JS-60033','color':'BLACK','price':660,'status':'Disponible','image':'public/catalog/monroe/gallery-1.webp'},
    {'slug':'hendrix','name':'HENDRIX','code':'NC-29026','color':'GOLD','price':660,'status':'Pocas piezas','image':'public/catalog/hendrix/gallery-1.webp'},
    {'slug':'gaga','name':'GAGA','code':'NC-29046','color':'RED','price':740,'status':'Pocas piezas','image':'public/catalog/gaga/gallery-1.webp'},
    {'slug':'winehouse','name':'WINEHOUSE','code':'YD-GN1127T','color':'BLACK/CRYSTAL','price':780,'status':'Pocas piezas','image':'public/catalog/winehouse/gallery-1.webp'},
    {'slug':'depp','name':'DEPP','code':'ZD-8809T','color':'GOLD','price':590,'status':'Disponible','image':'public/catalog/depp/gallery-1.webp'},
]
posts = [
    {'id':'legacy-post-01','date':'2026-06-05','format':'Instagram feed square','theme':'Brand launch / editorial','headline':'La noche empieza antes de salir.','sub':'Legacy — lentes importados para CDMX','asset':'legacy_ig_01_launch.png','source':'public/editorial/legacy-crew-hero.webp','caption':'La noche empieza antes de salir. Legacy reúne siluetas importadas, presencia medida y entrega directa en CDMX. Explora modelos desde $590 MXN.\n\n#LegacyCDMX #LentesDeSol #CDMX #OpticalNoir','cta':'Elegir mi Legacy'},
    {'id':'legacy-post-02','date':'2026-06-06','format':'Instagram feed square','theme':'Product spotlight','headline':'MONROE / BLACK','sub':'Negro limpio. Presencia inmediata. $660 MXN','asset':'legacy_ig_02_monroe.png','source':'public/catalog/monroe/gallery-1.webp','caption':'MONROE en negro: una silueta limpia para entrar sin explicar demasiado. Disponible en Legacy.\n\n#LegacyMonroe #LentesCDMX #LuxurySunglasses','cta':'Apartar para la noche'},
    {'id':'legacy-post-03','date':'2026-06-07','format':'Instagram feed square','theme':'Low stock urgency','headline':'Pocas piezas. Mucha presencia.','sub':'HENDRIX / GAGA / WINEHOUSE','asset':'legacy_ig_03_low_stock.png','source':'public/catalog/gaga/gallery-1.webp','caption':'Las piezas con más carácter no se quedan esperando. Hendrix, Gaga y Winehouse están en pocas piezas. Consulta color y disponibilidad.\n\n#LegacyDrop #CDMXStyle #LentesDeSol','cta':'Consultar disponibilidad'},
    {'id':'legacy-post-04','date':'2026-06-08','format':'Instagram feed square','theme':'Editorial archive','headline':'CDMX privada.','sub':'Un archivo para moverse después de oscuro.','asset':'legacy_ig_04_editorial.png','source':'public/editorial/whatsapp/legacy-whatsapp-13.webp','caption':'No es solo el modelo: es la forma de entrar. Legacy trabaja con una estética Optical Noir: negro, marfil, geometría y noche de CDMX.\n\n#OpticalNoir #LegacyCDMX','cta':'Ver novedades'},
    {'id':'legacy-post-05','date':'2026-06-09','format':'Instagram feed square','theme':'Buyer guide','headline':'Elige por actitud, no por tendencia.','sub':'Azul / Negro / Oro / Crystal','asset':'legacy_ig_05_guide.png','source':'public/catalog/lennon/gallery-1.webp','caption':'Guía rápida Legacy: azul para contraste, negro para presencia directa, oro para luz nocturna, crystal para precisión. El modelo correcto se nota antes de hablar.\n\n#GuiaLegacy #SunglassesMX','cta':'Explorar modelos'},
    {'id':'legacy-post-06','date':'2026-06-10','format':'Instagram feed square','theme':'Promo / entry price','headline':'Desde $590 MXN.','sub':'DEPP / GOLD — entrada al universo Legacy','asset':'legacy_ig_06_promo.png','source':'public/catalog/depp/gallery-1.webp','caption':'Entrar al universo Legacy no tiene que esperar. Modelos seleccionados desde $590 MXN, con entrega coordinada desde CDMX.\n\n#LegacyPromo #LentesImportados','cta':'Entrar a promos'},
]

def font(size, bold=False):
    candidates = ['C:/Windows/Fonts/georgia.ttf' if not bold else 'C:/Windows/Fonts/georgiab.ttf','C:/Windows/Fonts/arial.ttf' if not bold else 'C:/Windows/Fonts/arialbd.ttf']
    for c in candidates:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()

def cover(im, size):
    return ImageOps.fit(im.convert('RGB'), size, method=Image.Resampling.LANCZOS, centering=(0.5,0.5))

def draw_wrapped(draw, text, xy, max_width, fnt, fill, line_spacing=8):
    x,y=xy; words=text.split(); lines=[]; line=''
    for w in words:
        test=(line+' '+w).strip()
        if draw.textbbox((0,0), test, font=fnt)[2] <= max_width:
            line=test
        else:
            if line: lines.append(line)
            line=w
    if line: lines.append(line)
    for ln in lines:
        draw.text((x,y), ln, font=fnt, fill=fill)
        y += draw.textbbox((0,0), ln, font=fnt)[3] + line_spacing
    return y

for p in posts:
    src = legacy / p['source']
    im = Image.open(src)
    bg = Image.new('RGB',(1080,1080),'#050505')
    photo = cover(im,(650,1080))
    if p['id'] in ['legacy-post-02','legacy-post-03','legacy-post-05','legacy-post-06']:
        bg.paste(photo,(430,0)); x = 58; rect=(0,0,520,1080)
    else:
        bg.paste(photo,(0,0)); x = 594; rect=(520,0,1080,1080)
    d=ImageDraw.Draw(bg,'RGBA'); d.rectangle(rect, fill=(5,5,5,226))
    d=ImageDraw.Draw(bg)
    d.text((x,58),'LEGACY',font=font(42,True),fill='#F6F0E4')
    d.line((x,120,x+260,120),fill='#C78346',width=3)
    y=680
    y=draw_wrapped(d,p['headline'],(x,y),420,font(56,True),'#F6F0E4',10)
    y=draw_wrapped(d,p['sub'],(x,y+22),410,font(26),'#E6D8C0',6)
    d.text((x,990),p['cta'].upper(),font=font(22,True),fill='#C78346')
    bg.save(media / p['asset'], quality=94)

frames = []
for p in posts[:4]:
    img = Image.open(media / p['asset']).resize((1080,1080))
    frame_path = media / f"frame_{p['id']}.png"
    img.save(frame_path)
    frames.append(frame_path)
concat = media / 'reel_inputs.txt'
with concat.open('w', encoding='utf-8') as f:
    for frame in frames:
        f.write(f"file '{frame.as_posix()}'\n")
        f.write('duration 1.5\n')
    f.write(f"file '{frames[-1].as_posix()}'\n")
video = media / 'legacy_reel_01_optical_noir.mp4'
subprocess.run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(concat),'-vf','scale=1080:1080,format=yuv420p','-r','30',str(video)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

strategy = f'''# Legacy — Marketing Strategy Sprint

## Client context
Legacy is a Spanish-first luxury sunglass / glasswear brand for Mexico City. The current website frames the brand as **Optical Noir**: severe black and ivory contrast, thin circular geometry, editorial CDMX photography, and controlled lens color. The product catalog has 21 public models, with public prices from $590 MXN, Stripe checkout, direct CDMX delivery, and no public exact inventory counts.

## Business objective for the weekend
Produce a usable agency-grade marketing package that can launch Legacy's first social/content motion quickly: strategy, content calendar, Instagram post assets, copy, a video/reel direction, approval checklist, and next actions.

## Positioning
**Legacy is not a generic sunglasses shop. Legacy is a night-coded CDMX optical brand: curated imported frames, restrained luxury, and presence before explanation.**

### Primary message
"La noche empieza antes de salir."

### Supporting claims
- Lentes importados seleccionados para presencia editorial.
- Entrega coordinada desde CDMX.
- Modelos desde $590 MXN.
- Compra segura vía Stripe for available products.
- Consulta disponibilidad without exposing exact inventory.

## Target segments
1. **CDMX night-out buyers**: 20–35, fashion/social, wants an accessory with attitude before dinner/club/events.
2. **Editorial minimalists**: values black/ivory, restrained luxury, clean silhouettes, less logo noise.
3. **Gift / impulse buyers**: price-accessible luxury, wants fast checkout and delivery coordination.

## Channel strategy
- **Instagram feed** for brand world + product discovery.
- **Stories** for availability, polls, try-on questions, and checkout reminders.
- **Reels** for mood, motion, close-ups, and model sequencing.
- **Website/catalog** remains the conversion surface.
- **WhatsApp/DM** should handle consult models and availability without public counts.

## Brand guardrails
- Spanish-first.
- Avoid cheap discount language.
- Do not publish exact inventory counts, supplier/cost/margin, or internal operational details.
- No stock imagery if existing Legacy editorial/product assets can be used.
- Keep it expensive, calm, CDMX, night-coded.
'''
calendar = '''# Legacy — 10-Day Social Media Calendar

| Date | Channel | Post | Asset | Copy angle | CTA | Owner | Status |
|---|---|---|---|---|---|---|---|
| 2026-06-05 | Instagram Feed | Brand launch/editorial | legacy_ig_01_launch.png | La noche empieza antes de salir | Elegir mi Legacy | brand_content | ready |
| 2026-06-06 | Instagram Feed | MONROE spotlight | legacy_ig_02_monroe.png | Negro limpio, presencia inmediata | Apartar para la noche | brand_content | ready |
| 2026-06-07 | Instagram Feed + Stories | Low-stock character models | legacy_ig_03_low_stock.png | Pocas piezas / mucho carácter | Consultar disponibilidad | channel_execution | ready |
| 2026-06-08 | Instagram Feed | CDMX editorial archive | legacy_ig_04_editorial.png | Optical Noir / CDMX privada | Ver novedades | brand_content | ready |
| 2026-06-09 | Instagram Carousel | Buyer guide | legacy_ig_05_guide.png | Elegir por actitud, no tendencia | Explorar modelos | strategy_research | ready |
| 2026-06-10 | Instagram Feed | Entry-price promo | legacy_ig_06_promo.png | Desde $590 MXN, sin sonar barato | Entrar a promos | channel_execution | ready |
| 2026-06-11 | Stories | Poll: negro/oro/azul/crystal | reuse post 05 | Preference capture | Responder encuesta | analytics_performance | planned |
| 2026-06-12 | Reel | Optical Noir reel | legacy_reel_01_optical_noir.mp4 | Mood + product rhythm | Ver catálogo | brand_content | ready |
| 2026-06-13 | Instagram Feed | Checkout education | use cart/site screenshots | Pago seguro + entrega CDMX | Cerrar con Legacy | channel_execution | planned |
| 2026-06-14 | Stories | Availability follow-up | product cards | DM/WhatsApp availability | Consultar modelo | client_approval_ops | planned |

## Daily operating cadence
- Morning: publish feed post or story set.
- Afternoon: respond to DMs and note product interest by model.
- Evening: repost story and route shoppers to `/modelos`, `/novedades`, or `/promos`.
- End of day: capture metrics: reach, saves, profile visits, link clicks, DMs, checkout attempts.
'''
copy_pack = '# Legacy — Instagram Copy Pack\n\n'
for p in posts:
    copy_pack += f"## {p['id']} — {p['theme']}\n- **Date:** {p['date']}\n- **Format:** {p['format']}\n- **Visual:** `{p['asset']}`\n- **Headline:** {p['headline']}\n- **Caption:**\n\n{p['caption']}\n\n- **CTA:** {p['cta']}\n\n"
creative = '''# Legacy — Creative Direction Brief

## Visual system
- Backgrounds: ink/obsidian black, ivory type, bone surfaces.
- Accent: copper/amber rule lines, never loud gradients.
- Photography: existing Legacy product/editorial assets only.
- Layout: luxury catalog, not marketing template. Large image field + restrained type.
- Typography direction: Bodoni-like editorial headlines, clean sans body/CTA.

## Instagram asset rules
1. Use square 1080x1080 for feed.
2. Keep one dominant image, one strong line, one CTA.
3. Never publish exact stock counts.
4. For sold-out/consult models say "Consultar", not "agotado".
5. Captions should sound CDMX, editorial, and calm; avoid over-explaining.

## Reel direction: Optical Noir 12s
- 0–2s: hero crew/night image, line "La noche empieza antes de salir".
- 2–5s: MONROE close-up, line "Negro limpio".
- 5–8s: GAGA/HENDRIX low-stock character, line "Pocas piezas".
- 8–10s: CDMX editorial archive, line "CDMX privada".
- 10–12s: brand card, CTA "Elegir mi Legacy".

A simple first-cut MP4 has been generated as `legacy_reel_01_optical_noir.mp4` from the approved site assets.
'''
approval = '''# Legacy — Client Approval Packet

## Deliverables ready for review
- Marketing strategy sprint
- 10-day social media calendar
- 6 Instagram square post mockups
- Instagram caption/copy pack
- Creative direction brief
- 12-second reel/storyboard first cut
- Campaign launch package

## Decisions needed
1. Confirm the primary line: "La noche empieza antes de salir."
2. Confirm whether posts can use current public product prices.
3. Confirm posting channels: Instagram feed, stories, reels.
4. Confirm DM/WhatsApp handling for availability questions.
5. Confirm whether consult models should be positioned as "Consultar" only.

## Risk notes
- Do not expose exact inventory counts.
- Do not use raw client files directly; use optimized public derivatives.
- Avoid discount-heavy language; Legacy should feel like restrained luxury.
- Stripe/checkout claims should stay factual and tied to the current website implementation.
'''
package = '''# Legacy — Campaign Launch Package

## Launch theme
**La noche empieza antes de salir.**

## Package contents
1. Strategy: Optical Noir CDMX positioning.
2. Content calendar: 10-day cadence from launch/editorial/product/availability/promo.
3. Media: six 1080x1080 Instagram feed assets using existing Legacy imagery.
4. Copy: six captions and CTAs, Spanish-first.
5. Video: first-cut square reel built from approved site assets.
6. Approval: decision packet and risk checklist.

## Recommended immediate execution
- Today: approve strategy + first two posts; publish brand launch and MONROE spotlight.
- Tomorrow: publish low-stock character model post and schedule next week’s calendar.
- By Sunday: approve reel and buyer-guide carousel; start measuring DMs/profile visits/clicks.

## Measurement plan
- Reach and saves per post.
- Profile visits and website link clicks.
- DMs by model name.
- Cart adds and checkout attempts for available models.
- Manual notes for requested colors/models.
'''
files = {
 'legacy_marketing_strategy.md': strategy,
 'legacy_social_media_calendar.md': calendar,
 'legacy_instagram_copy_pack.md': copy_pack,
 'legacy_creative_direction_brief.md': creative,
 'legacy_client_approval_packet.md': approval,
 'legacy_campaign_launch_package.md': package,
 'legacy_brand_context.json': json.dumps({'brand':brand,'products':products,'posts':posts}, indent=2, ensure_ascii=False),
}
for name, content in files.items():
    (root / name).write_text(content, encoding='utf-8')
manifest = {
    'root': str(root),
    'media_dir': str(media),
    'brand': brand,
    'products_used': products,
    'posts': posts,
    'deliverable_files': sorted(files.keys()),
    'media_files': sorted([p.name for p in media.glob('*') if p.suffix.lower() in ['.png','.mp4'] and not p.name.startswith('frame_')]),
}
(root / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps({'root':str(root),'deliverable_files':manifest['deliverable_files'],'media_files':manifest['media_files']}, indent=2))
