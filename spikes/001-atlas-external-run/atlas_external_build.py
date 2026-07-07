from __future__ import annotations

import html
import json
import textwrap
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
ASSETS = OUT / "assets"
OUT.mkdir(parents=True, exist_ok=True)
ASSETS.mkdir(parents=True, exist_ok=True)

log = json.loads((ROOT / "prompts_and_tool_log.json").read_text(encoding="utf-8"))

client_sections = [
    {
        "title": "Resumen ejecutivo",
        "body": "Legacy Optical Noir propone un lanzamiento de fin de semana para presentar lentes de sol con una lectura editorial: oscuro, pulido, seguro y fácil de usar en CDMX. El paquete está listo para revisión creativa: dirección visual, seis assets base, copy sugerido y checklist de aprobación antes de publicar.",
    },
    {
        "title": "Concepto creativo",
        "body": "La idea central es tratar los lentes como una pieza que define el look, no como accesorio secundario. El mundo visual combina acetato negro, reflejos controlados, piedra, vidrio ahumado, metal cálido y una atmósfera nocturna premium. El resultado debe sentirse sobrio y deseable, sin caer en lujo genérico ni promoción ruidosa.",
    },
    {
        "title": "Dirección visual",
        "body": "Usar fondos oscuros, superficies reflectantes, detalles macro y composiciones con espacio limpio para copy posterior. Las imágenes no deben incluir personas, logos ni texto incrustado. La edición final puede sumar titulares y precios fuera de la imagen, en layout aprobado.",
    },
    {
        "title": "Copy sugerido",
        "body": "Caption 1: El fin de semana se ve mejor en negro. Optical Noir ya está listo para revisión.\nCaption 2: Lentes con presencia, sin ruido. Piezas sobrias para salir, manejar o elevar un look diario.\nCTA: ¿Quieres que te apartemos un modelo o prefieres ver dos opciones más?",
    },
    {
        "title": "Checklist de lanzamiento",
        "body": "1. Aprobar dirección visual. 2. Elegir 3–4 assets para publicación inicial. 3. Confirmar modelos disponibles y precios. 4. Preparar stories con CTA de DM/WhatsApp. 5. Publicar sólo después de aprobación y registrar respuestas, apartados y ventas.",
    },
    {
        "title": "Decisión solicitada",
        "body": "Aprobar si Optical Noir debe avanzar con este estilo visual, tono Spanish-first y ruta de lanzamiento con aprobación previa. Si el arte se aprueba, el siguiente paso es adaptar layouts con copy final y piezas listas para canal.",
    },
]

asset_rows = []
for idx, item in enumerate(log["image_prompts"], start=1):
    filename = f"legacy_optical_noir_external_{idx:02d}.png"
    dest = ASSETS / filename
    urllib.request.urlretrieve(item["result"], dest)
    # Normalize image format/size for package consistency.
    img = Image.open(dest).convert("RGB")
    img.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (1400, 1400), (7, 6, 5))
    x = (1400 - img.width) // 2
    y = (1400 - img.height) // 2
    canvas.paste(img, (x, y))
    canvas.save(dest, quality=94)
    asset_rows.append({"post": idx, "filename": f"assets/{filename}", "slot": item["slot"], "prompt": item["prompt"], "source_url": item["result"]})

# Contact sheet for QA/comparison.
thumbs = []
for row in asset_rows:
    p = OUT / row["filename"]
    im = Image.open(p).convert("RGB").resize((360, 360), Image.Resampling.LANCZOS)
    thumbs.append((row, im))
sheet = Image.new("RGB", (3 * 420, 2 * 455), (14, 12, 10))
d = ImageDraw.Draw(sheet)
for i, (row, im) in enumerate(thumbs):
    x = (i % 3) * 420 + 30
    y = (i // 3) * 455 + 30
    sheet.paste(im, (x, y))
    d.text((x, y + 370), f"Post {row['post']:02d} — {row['slot'].split(' / ')[-1]}", fill=(238, 224, 198))
sheet.save(OUT / "asset_contact_sheet.png", quality=94)

css = """
:root{color-scheme:dark;--bg:#070605;--panel:#15110e;--ink:#f7ecd6;--muted:#cbb99c;--line:#a66a2a66;--accent:#d8a253}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0%,#24170d,#070605 45%,#030303);color:var(--ink);font-family:Inter,Arial,sans-serif;line-height:1.55}main{max-width:1120px;margin:0 auto;padding:56px 36px 72px}.hero{padding:36px;border:1px solid var(--line);border-radius:28px;background:linear-gradient(135deg,#17110d,#090807 62%,#10231f);box-shadow:0 24px 80px #0008}h1{font-size:46px;line-height:1.02;margin:0 0 16px}.dek{font-size:19px;color:var(--muted);max-width:820px}.eyebrow{text-transform:uppercase;letter-spacing:.13em;color:var(--accent);font-size:12px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin-top:22px}.card{background:#15110ee8;border:1px solid var(--line);border-radius:22px;padding:24px}.card h2{margin:0 0 10px;color:#ffe3b4}.gallery{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.asset{border:1px solid var(--line);border-radius:20px;overflow:hidden;background:#0b0908}.asset img{width:100%;display:block;aspect-ratio:1/1;object-fit:cover}.asset div{padding:13px}.asset p{margin:.25rem 0;color:var(--muted);font-size:13px}.footer{color:var(--muted);font-size:13px;margin-top:24px}
"""
assets_html = "\n".join(
    f"""<article class='asset'><img src='{html.escape(row['filename'])}' alt='Legacy Optical Noir Post {row['post']:02d}'><div><strong>Post {row['post']:02d}</strong><p>{html.escape(row['slot'])}</p></div></article>"""
    for row in asset_rows
)
sections_html = "\n".join(
    f"<section class='card'><p class='eyebrow'>Legacy Optical Noir</p><h2>{html.escape(sec['title'])}</h2><p>{html.escape(sec['body']).replace(chr(10), '<br>')}</p></section>"
    for sec in client_sections
)
html_text = f"""<!doctype html><html lang='es'><head><meta charset='utf-8'><title>Legacy Optical Noir — Paquete de aprobación</title><style>{css}</style></head><body><main><header class='hero'><p class='eyebrow'>Paquete de aprobación</p><h1>Legacy Optical Noir</h1><p class='dek'>Dirección creativa y assets base para revisar antes de producción. Sin publicación en vivo; el siguiente paso requiere aprobación explícita.</p></header><section class='card'><p class='eyebrow'>Galería</p><h2>Assets propuestos</h2><div class='gallery'>{assets_html}</div></section><div class='grid'>{sections_html}</div><p class='footer'>Preparado como spike externo de Atlas para comparar calidad de prompts, herramientas y artefactos contra la corrida interna de ForgeGraph.</p></main></body></html>"""
(OUT / "Legacy_Optical_Noir_Approval_Handoff.html").write_text(html_text, encoding="utf-8")

# PDF generated as a polished visual proof using PIL pages.
def font(size: int, bold: bool = False):
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except OSError:
            pass
    return ImageFont.load_default()

F_TITLE = font(52, True); F_H2 = font(30, True); F_BODY = font(22); F_SMALL = font(16)
PAGE = (1240, 1754)
BG = (8, 7, 6); INK = (248, 236, 216); MUTED = (205, 185, 156); ACCENT = (216, 162, 83); PANEL = (21, 17, 14)
pages = []

def new_page():
    im = Image.new("RGB", PAGE, BG)
    dr = ImageDraw.Draw(im)
    dr.rectangle([60, 60, PAGE[0]-60, PAGE[1]-60], outline=(118, 78, 42), width=2)
    return im, dr

def draw_wrapped(dr, text, xy, width_chars, fill=INK, fnt=F_BODY, spacing=10):
    x, y = xy
    for para in text.split("\n"):
        lines = textwrap.wrap(para, width=width_chars) or [""]
        for line in lines:
            dr.text((x, y), line, font=fnt, fill=fill)
            y += fnt.size + spacing
        y += spacing
    return y

page, dr = new_page()
dr.text((100, 110), "Legacy Optical Noir", font=F_TITLE, fill=INK)
dr.text((100, 178), "Paquete de aprobación", font=F_H2, fill=ACCENT)
y = draw_wrapped(dr, "Dirección creativa y assets base para revisar antes de producción. Sin publicación en vivo; el siguiente paso requiere aprobación explícita.", (100, 245), 72, MUTED, F_BODY)
# paste 2x3 thumbnails
for i, row in enumerate(asset_rows):
    im = Image.open(OUT / row["filename"]).convert("RGB").resize((320, 320), Image.Resampling.LANCZOS)
    x = 100 + (i % 3) * 360
    y0 = 430 + (i // 3) * 420
    page.paste(im, (x, y0))
    dr.text((x, y0 + 332), f"Post {row['post']:02d}", font=F_SMALL, fill=ACCENT)
    dr.text((x, y0 + 356), row['slot'].split(' / ')[-1], font=F_SMALL, fill=MUTED)
pages.append(page)

page, dr = new_page(); y = 105
for sec in client_sections[:3]:
    dr.text((100, y), sec["title"], font=F_H2, fill=ACCENT); y += 48
    y = draw_wrapped(dr, sec["body"], (100, y), 78, INK, F_BODY); y += 34
pages.append(page)

page, dr = new_page(); y = 105
for sec in client_sections[3:]:
    dr.text((100, y), sec["title"], font=F_H2, fill=ACCENT); y += 48
    y = draw_wrapped(dr, sec["body"], (100, y), 78, INK, F_BODY); y += 34
pages.append(page)

pdf_path = OUT / "Legacy_Optical_Noir_Approval_Handoff.pdf"
pages[0].save(pdf_path, save_all=True, append_images=pages[1:])

manifest = {
    "run_id": log["run_id"],
    "source": "atlas_external_spike.hermes_tools",
    "purpose": "Compare external Atlas-style prompt/tool execution against ForgeGraph internal run.",
    "client_files": ["Legacy_Optical_Noir_Approval_Handoff.html", "Legacy_Optical_Noir_Approval_Handoff.pdf"] + [r["filename"] for r in asset_rows],
    "assets": asset_rows,
    "tool_log_file": "internal_prompts_and_tool_log.json",
    "quality_note": "Generated with direct real-image artifact generation prompts, not ForgeGraph codex_spec_renderer placeholder path.",
}
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
(OUT / "internal_prompts_and_tool_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")

zip_path = ROOT / "Legacy_Optical_Noir_EXTERNAL_ATLAS_SPIKE.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for p in OUT.rglob("*"):
        if p.is_file():
            z.write(p, p.relative_to(OUT).as_posix())

print(json.dumps({
    "zip_path": str(zip_path),
    "html": str(OUT / "Legacy_Optical_Noir_Approval_Handoff.html"),
    "pdf": str(pdf_path),
    "contact_sheet": str(OUT / "asset_contact_sheet.png"),
    "entries": sorted([p.relative_to(OUT).as_posix() for p in OUT.rglob('*') if p.is_file()]),
    "zip_size": zip_path.stat().st_size,
}, indent=2))
