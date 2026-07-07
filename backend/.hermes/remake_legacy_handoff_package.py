from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import textwrap
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Flowable,
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path.cwd()
SRC = ROOT / ".hermes" / "attached_legacy_optical_noir_handoff"
OUT_BASE = ROOT / ".hermes" / "remade_legacy_optical_noir_handoff"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
OUT = OUT_BASE / f"legacy_optical_noir_handoff_{STAMP}"
PACKAGE = OUT / "client_package"
DELIVERABLES = PACKAGE / "deliverables"
ASSETS = PACKAGE / "assets"
HERO_URL = "https://v3b.fal.media/files/b/0a9dc19e/YYkaiYSDQ3jxanpunnMzt_yYrm2AvI.png"

DOCS = [
    ("codex_client_approval_packet.md", "Client Approval Packet", "Final go/no-go, decisions, launch gates", "01_client_approval_packet.html"),
    ("codex_strategy_brief.md", "Strategy & Research Brief", "Positioning, audience, guardrails", "02_strategy_research_brief.html"),
    ("codex_brand_content_pack.md", "Brand Content Pack", "Campaign lines, captions, CTAs", "03_brand_content_pack.html"),
    ("codex_channel_execution_calendar.md", "Channel Execution Calendar", "Weekend routing plan", "04_channel_execution_calendar.html"),
    ("codex_crm_response_scripts.md", "CRM / WhatsApp Scripts", "Boutique response flows", "05_crm_whatsapp_scripts.html"),
    ("codex_measurement_plan.md", "Measurement Plan", "KPIs, UTMs, readout model", "06_measurement_plan.html"),
    ("codex_qa_report.md", "Launch QA Report", "Claims, connector, and client-safety checks", "07_launch_qa_report.html"),
]

CSS = """
:root{--bg:#070605;--panel:#14100d;--panel2:#1d1712;--ink:#f8eedf;--muted:#cbb99c;--line:#b47a3d5c;--gold:#d39a4c;--copper:#a86532;--green:#153c35;--paper:#fff8ee;--paper-ink:#201915}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:'DM Sans',Inter,system-ui,-apple-system,Segoe UI,Arial,sans-serif;background:radial-gradient(circle at 18% -10%,#322014 0,#0d0907 40%,#030303 100%);color:var(--ink);line-height:1.55}.wrap{max-width:1180px;margin:0 auto;padding:40px 28px 72px}.hero{position:relative;min-height:460px;border:1px solid var(--line);background:linear-gradient(90deg,#080604 0,#080604e6 42%,#08060455 100%),var(--hero) center/cover no-repeat;border-radius:0;box-shadow:0 32px 100px #000a;overflow:hidden}.hero-inner{position:absolute;left:42px;right:42px;bottom:38px;max-width:780px}.eyebrow{letter-spacing:.16em;text-transform:uppercase;color:var(--gold);font-size:12px;font-weight:800;margin:0 0 12px}.hero h1{font-size:64px;line-height:.98;letter-spacing:-.055em;text-transform:uppercase;font-weight:300;margin:0 0 18px}.dek{font-size:20px;color:#ead9c0;max-width:780px}.topbar{display:flex;justify-content:space-between;gap:16px;margin:22px 0;color:var(--muted);font-size:13px}.badge{border:1px solid var(--line);padding:8px 10px;text-transform:uppercase;letter-spacing:.1em;color:#f3d6a4}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}.card{background:linear-gradient(180deg,var(--panel),#0d0a08);border:1px solid var(--line);padding:24px;box-shadow:0 18px 50px #0004}.card h2{font-size:28px;line-height:1.05;margin:4px 0 12px;font-weight:400;color:#ffe7c6}.card h3{margin:18px 0 8px;color:#f6cf93}.muted{color:var(--muted)}.stat{font-size:44px;line-height:1;font-weight:300;color:#ffe7c6}.doc-card{display:flex;flex-direction:column;min-height:210px}.doc-card a{color:var(--ink);text-decoration:none}.doc-card .num{color:var(--gold);font-family:ui-monospace,monospace}.doc-card p{color:var(--muted)}.cta{display:inline-block;margin-top:auto;border:1px solid #f0bd75;padding:10px 12px;color:#ffe7c6;text-decoration:none;text-transform:uppercase;letter-spacing:.1em;font-size:12px}.section{margin-top:22px}.approval{background:linear-gradient(135deg,#23170e,#102d28);border-color:#d39a4c99}.approval ul{margin:8px 0 0;padding-left:18px}.paper{background:var(--paper);color:var(--paper-ink);padding:42px 48px;max-width:980px;margin:0 auto}.paper h1{font-size:42px;line-height:1.05;text-transform:uppercase;font-weight:300;letter-spacing:-.035em}.paper h2{font-size:27px;margin-top:34px;border-top:1px solid #dcc9ad;padding-top:22px}.paper h3{font-size:20px;color:#5f3c1d}.paper p,.paper li{font-size:15px}.paper table{width:100%;border-collapse:collapse;margin:16px 0 22px;font-size:14px}.paper th{background:#211814;color:#fff2dd;text-align:left}.paper th,.paper td{border:1px solid #d8c3a5;padding:9px 10px;vertical-align:top}.paper blockquote{margin:18px 0;padding:14px 18px;border-left:4px solid #a86532;background:#f1e4d2}.paper code{background:#ead8bf;padding:2px 5px}.pill{display:inline-block;padding:4px 8px;background:#261914;color:#ffe7c6;margin:2px 4px 2px 0}.footer{margin-top:28px;color:var(--muted);font-size:13px}@media(max-width:850px){.grid,.two{grid-template-columns:1fr}.hero h1{font-size:44px}.hero-inner{left:24px;right:24px}.paper{padding:28px 22px}}@media print{body{background:white}.wrap{padding:0}.hero,.card{box-shadow:none}.no-print{display:none}.paper{max-width:none}}
"""


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def inline_md(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<a href=\"\2\">\1</a>", text)
    return text


def parse_table(lines: list[str], start: int) -> tuple[str, int]:
    rows = []
    i = start
    while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
        raw = lines[i].strip().strip("|")
        cells = [c.strip() for c in raw.split("|")]
        rows.append(cells)
        i += 1
    if len(rows) >= 2 and all(re.fullmatch(r":?-{3,}:?", c or "---") for c in rows[1]):
        header, body = rows[0], rows[2:]
    else:
        header, body = rows[0], rows[1:]
    out = ["<table><thead><tr>"]
    out += [f"<th>{inline_md(c)}</th>" for c in header]
    out += ["</tr></thead><tbody>"]
    for row in body:
        out.append("<tr>" + "".join(f"<td>{inline_md(c)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out), i


def md_to_html(md: str) -> str:
    lines = md.replace("\r\n", "\n").split("\n")
    out, para, in_ul, in_ol = [], [], False, False

    def flush_para():
        nonlocal para
        if para:
            out.append("<p>" + inline_md(" ".join(x.strip() for x in para)) + "</p>")
            para = []

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            flush_para(); close_lists(); i += 1; continue
        if stripped == "---":
            flush_para(); close_lists(); out.append("<hr>"); i += 1; continue
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_para(); close_lists(); table, i = parse_table(lines, i); out.append(table); continue
        if stripped.startswith("#"):
            flush_para(); close_lists()
            level = min(3, len(stripped) - len(stripped.lstrip("#")))
            title = stripped[level:].strip()
            out.append(f"<h{level} id='{slugify(title)}'>{inline_md(title)}</h{level}>")
            i += 1; continue
        if stripped.startswith(">"):
            flush_para(); close_lists(); out.append(f"<blockquote>{inline_md(stripped[1:].strip())}</blockquote>"); i += 1; continue
        m = re.match(r"^[-*]\s+(.*)", stripped)
        if m:
            flush_para()
            if in_ol:
                out.append("</ol>"); in_ol = False
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append(f"<li>{inline_md(m.group(1))}</li>")
            i += 1; continue
        m = re.match(r"^\d+\.\s+(.*)", stripped)
        if m:
            flush_para()
            if in_ul:
                out.append("</ul>"); in_ul = False
            if not in_ol:
                out.append("<ol>"); in_ol = True
            out.append(f"<li>{inline_md(m.group(1))}</li>")
            i += 1; continue
        para.append(stripped)
        i += 1
    flush_para(); close_lists()
    return "\n".join(out)


def page(title: str, body: str, hero: bool = False) -> str:
    hero_css = ""
    if (ASSETS / "legacy_optical_noir_hero.png").exists():
        hero_css = "--hero:url('assets/legacy_optical_noir_hero.png');"
    return f"<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>{html.escape(title)}</title><link href='https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&display=swap' rel='stylesheet'><style>{CSS}</style></head><body style=\"{hero_css}\">{body}</body></html>"


def download_hero() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    out = ASSETS / "legacy_optical_noir_hero.png"
    try:
        urllib.request.urlretrieve(HERO_URL, out)
        # normalize reasonable package size
        img = Image.open(out).convert("RGB")
        img.thumbnail((1800, 1000))
        img.save(out, quality=92)
    except Exception as exc:
        print(f"WARN hero download failed: {exc}")
        img = Image.new("RGB", (1600, 900), "#080604")
        draw = ImageDraw.Draw(img)
        for y in range(900):
            c = int(8 + y * 0.035)
            draw.line([(0, y), (1600, y)], fill=(c, max(6, c-3), max(4, c-8)))
        draw.ellipse((980, 330, 1380, 530), outline=(195, 128, 66), width=8)
        draw.ellipse((1180, 330, 1580, 530), outline=(195, 128, 66), width=8)
        draw.line((1350, 430, 1210, 430), fill=(195, 128, 66), width=8)
        img.save(out, quality=92)


def make_preview_card() -> None:
    out = ASSETS / "legacy_optical_noir_preview_card.png"
    W, H = 1600, 1000
    img = Image.open(ASSETS / "legacy_optical_noir_hero.png").convert("RGB").resize((W, H))
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, 950, H), fill=(5, 4, 3, 215))
    draw.rectangle((80, 110, 1520, 900), outline=(211, 154, 76, 180), width=2)
    try:
        title = ImageFont.truetype("arial.ttf", 82)
        small = ImageFont.truetype("arial.ttf", 28)
        med = ImageFont.truetype("arial.ttf", 40)
    except Exception:
        title = small = med = ImageFont.load_default()
    draw.text((120, 160), "LEGACY", fill=(255, 236, 210), font=med)
    draw.text((120, 235), "OPTICAL\nNOIR", fill=(255, 236, 210), font=title, spacing=8)
    draw.text((120, 475), "Client handoff package", fill=(211, 154, 76), font=med)
    draw.text((120, 560), "Strategy • Content • CRM • Calendar • Measurement • QA", fill=(228, 204, 170), font=small)
    draw.text((120, 820), "Approval-gated. Client-ready. No live publishing claims.", fill=(228, 204, 170), font=small)
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    img.save(out, quality=93)


def build_html_pages() -> list[dict]:
    rendered = []
    for source, title, desc, out_name in DOCS:
        md = (SRC / source).read_text(encoding="utf-8")
        content = md_to_html(md)
        body = f"<main class='wrap'><article class='paper'><p class='eyebrow'>Legacy Optical Noir</p>{content}<p class='footer'>Rendered from {html.escape(source)} into a client-facing HTML deliverable. Production launch requires explicit approval.</p></article></main>"
        (DELIVERABLES / out_name).write_text(page(title, body), encoding="utf-8")
        rendered.append({"title": title, "description": desc, "source_reference": source, "file": f"deliverables/{out_name}"})
    return rendered


def build_index(rendered: list[dict]) -> None:
    cards = []
    for idx, item in enumerate(rendered, start=1):
        cards.append(f"""
        <section class='card doc-card'>
          <p class='eyebrow'><span class='num'>{idx:02d}</span> / deliverable</p>
          <h2><a href='{html.escape(item['file'])}'>{html.escape(item['title'])}</a></h2>
          <p>{html.escape(item['description'])}</p>
          <a class='cta' href='{html.escape(item['file'])}'>Open deliverable</a>
        </section>""")
    body = f"""
    <main class='wrap'>
      <section class='hero'><div class='hero-inner'><p class='eyebrow'>Atlas / ForgeGraph diagnostic remake</p><h1>Legacy Optical Noir handoff package</h1><p class='dek'>A professional remake of the earlier multi-department package: strategy, content, channel plan, CRM scripts, measurement, QA, and client approval are separated into reviewable artifacts and wrapped in a premium client-facing shell.</p></div></section>
      <div class='topbar'><span class='badge'>Approval gated</span><span>Generated {STAMP} UTC</span></div>
      <section class='two section'>
        <div class='card approval'><p class='eyebrow'>Decision first</p><h2>What Mike / Legacy can approve</h2><ul><li>Optical Noir positioning: quiet premium CDMX eyewear</li><li>Spanish-first restrained luxury tone</li><li>Weekend channel plan with manual publishing gates</li><li>WhatsApp/DM concierge conversion path</li><li>Connector/access gaps before production execution</li></ul></div>
        <div class='card'><p class='eyebrow'>Why this feels more professional</p><h2>Package architecture</h2><p class='muted'>The work is not compressed into one plain strategy memo. It is organized as a client handoff system: executive approval first, then department artifacts, launch gates, QA, and provenance.</p><p><span class='pill'>7 deliverables</span><span class='pill'>HTML/PDF</span><span class='pill'>manifest</span><span class='pill'>hero visual</span></p></div>
      </section>
      <section class='grid section'>{''.join(cards)}</section>
      <section class='two section'>
        <div class='card'><p class='eyebrow'>Included visual</p><h2>Fresh hero asset</h2><p class='muted'>Generated with Hermes image generation for this remake, then packaged locally as a supporting campaign visual.</p><p><code>assets/legacy_optical_noir_hero.png</code></p></div>
        <div class='card'><p class='eyebrow'>Client safety</p><h2>Production boundaries</h2><ul><li>No claim that anything was published live.</li><li>No connector limitations hidden inside deliverable planning.</li><li>No Markdown files in the client ZIP.</li><li>Manifest separates source references from client-facing files.</li></ul></div>
      </section>
      <p class='footer'>Diagnostic remake produced from the attached earlier package content and a fresh Hermes-generated hero image. It is suitable for internal review of formatting/product gaps, not an assertion of live client delivery.</p>
    </main>"""
    (PACKAGE / "Legacy_Optical_Noir_Executive_Handoff.html").write_text(page("Legacy Optical Noir Executive Handoff", body), encoding="utf-8")


class HR(Flowable):
    def __init__(self, width=6.5 * inch, color=colors.HexColor("#c18b4e")):
        super().__init__(); self.width = width; self.color = color
    def draw(self):
        self.canv.setStrokeColor(self.color); self.canv.setLineWidth(0.8); self.canv.line(0, 0, self.width, 0)


def para_from_md_line(line: str) -> str:
    text = html.escape(line.strip())
    text = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    return text


def pdf_doc() -> None:
    pdf = PACKAGE / "Legacy_Optical_Noir_Handoff.pdf"
    doc = SimpleDocTemplate(str(pdf), pagesize=letter, rightMargin=0.65*inch, leftMargin=0.65*inch, topMargin=0.65*inch, bottomMargin=0.65*inch)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="NoirTitle", parent=styles["Title"], fontName="Helvetica", fontSize=32, leading=34, textColor=colors.HexColor("#201713"), alignment=TA_LEFT, spaceAfter=14))
    styles.add(ParagraphStyle(name="NoirH1", parent=styles["Heading1"], fontSize=21, leading=24, textColor=colors.HexColor("#7b471f"), spaceBefore=16, spaceAfter=8))
    styles.add(ParagraphStyle(name="NoirH2", parent=styles["Heading2"], fontSize=15, leading=18, textColor=colors.HexColor("#201713"), spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="NoirBody", parent=styles["BodyText"], fontSize=9.5, leading=12.5, textColor=colors.HexColor("#201713"), spaceAfter=5))
    styles.add(ParagraphStyle(name="NoirSmall", parent=styles["BodyText"], fontSize=8.5, leading=10.5, textColor=colors.HexColor("#6d6258"), spaceAfter=4))
    story = []
    hero = ASSETS / "legacy_optical_noir_hero.png"
    if hero.exists():
        story.append(RLImage(str(hero), width=6.45*inch, height=3.35*inch))
        story.append(Spacer(1, 0.18*inch))
    story.append(Paragraph("LEGACY OPTICAL NOIR", styles["NoirTitle"]))
    story.append(Paragraph("Executive handoff package — strategy, content, channel plan, CRM, measurement, QA, and approval gates.", styles["NoirBody"]))
    story.append(HR()); story.append(Spacer(1, 0.14*inch))
    rows = [["Deliverable", "Purpose", "File"]] + [[d[1], d[2], d[3]] for d in DOCS]
    tbl = Table(rows, colWidths=[2.1*inch, 2.45*inch, 1.75*inch], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#201713")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.HexColor("#fff2dd")),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#d5bea0")),
        ("BACKGROUND", (0,1), (-1,-1), colors.HexColor("#fff8ee")),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)
    ]))
    story.append(tbl)
    story.append(PageBreak())

    for source, title, desc, _out_name in DOCS:
        story.append(Paragraph(title, styles["NoirH1"]))
        story.append(Paragraph(desc, styles["NoirSmall"]))
        story.append(HR()); story.append(Spacer(1, 0.1*inch))
        lines = (SRC / source).read_text(encoding="utf-8").splitlines()
        for line in lines:
            s = line.strip()
            if not s or s == "---":
                story.append(Spacer(1, 0.05*inch)); continue
            if s.startswith("#"):
                level = len(s) - len(s.lstrip("#"))
                txt = para_from_md_line(s[level:].strip())
                story.append(Paragraph(txt, styles["NoirH1" if level <= 2 else "NoirH2"]))
            elif s.startswith("|"):
                # Skip markdown table syntax in PDF body; HTML pages preserve full tables.
                continue
            elif re.match(r"^[-*]\s+", s):
                story.append(Paragraph("• " + para_from_md_line(re.sub(r"^[-*]\s+", "", s)), styles["NoirBody"]))
            elif re.match(r"^\d+\.\s+", s):
                story.append(Paragraph(para_from_md_line(s), styles["NoirBody"]))
            elif s.startswith(">"):
                story.append(Paragraph("“" + para_from_md_line(s[1:].strip()) + "”", styles["NoirBody"]))
            else:
                story.append(Paragraph(para_from_md_line(s), styles["NoirBody"]))
        story.append(PageBreak())
    doc.build(story)


def build_email_and_manifest(rendered: list[dict]) -> dict:
    email_html = """<!doctype html><html><body style=\"font-family:Arial,sans-serif;color:#211814\"><h1>Legacy Optical Noir — handoff listo para revisión</h1><p>Mike,</p><p>Adjunto va el paquete de handoff remade para revisar formato y estructura contra el output actual de ForgeGraph.</p><ul><li>Executive handoff HTML/PDF</li><li>7 entregables departamentales renderizados a HTML</li><li>Hero visual fresco</li><li>Manifest con linaje y política de formatos</li></ul><p>La recomendación es revisar primero el approval packet y luego strategy/channel/calendar.</p><p>— Atlas / ForgeGraph diagnostic remake</p></body></html>"""
    (PACKAGE / "email_body.html").write_text(email_html, encoding="utf-8")
    (PACKAGE / "email_body.txt").write_text("Legacy Optical Noir — handoff listo para revisión\n\nAdjunto paquete remade para revisar formato/estructura contra el output actual de ForgeGraph. Incluye executive handoff HTML/PDF, 7 entregables HTML, hero visual y manifest.\n", encoding="utf-8")
    manifest = {
        "client": "Legacy",
        "campaign": "Optical Noir",
        "source": "hermes_diagnostic_remake.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_package": "C:/Users/mathi/Downloads/legacy_optical_noir_handoff_package.zip",
        "hero_image_source": {"tool": "image_generate", "url": HERO_URL, "local_file": "assets/legacy_optical_noir_hero.png"},
        "rendering_tools": ["Python custom markdown-to-HTML renderer", "CSS based on premium BMW/noir design tokens", "Pillow preview card generation", "ReportLab PDF generation", "zipfile packaging"],
        "client_files_policy": "Client ZIP contains HTML/PDF/PNG/TXT/JSON only; source Markdown from attached package was used as input but not included.",
        "deliverables": rendered,
        "production_boundary": "No live publishing, sending, scheduling, connector success, or performance result is claimed.",
    }
    (PACKAGE / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def zip_package() -> Path:
    zip_path = OUT / "Legacy_Optical_Noir_REMADE_PROFESSIONAL_PACKAGE.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PACKAGE.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(PACKAGE).as_posix())
    return zip_path


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"Missing source package extraction: {SRC}")
    if OUT.exists():
        shutil.rmtree(OUT)
    DELIVERABLES.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    download_hero()
    make_preview_card()
    rendered = build_html_pages()
    build_index(rendered)
    pdf_doc()
    manifest = build_email_and_manifest(rendered)
    zip_path = zip_package()
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    entries = []
    with zipfile.ZipFile(zip_path) as zf:
        entries = zf.namelist()
    print(json.dumps({
        "out_dir": str(OUT),
        "zip": str(zip_path),
        "zip_sha256": sha,
        "zip_size": zip_path.stat().st_size,
        "entry_count": len(entries),
        "entries": entries,
        "manifest_client_files_policy": manifest["client_files_policy"],
    }, indent=2))

if __name__ == "__main__":
    main()
