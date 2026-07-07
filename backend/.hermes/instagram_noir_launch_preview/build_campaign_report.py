from __future__ import annotations

import base64
import json
import subprocess
import textwrap
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path.cwd()
OUT = ROOT / ".hermes" / "legacy_campaign_report_first_run"
ASSETS = OUT / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)
SRC_DIR = ROOT / ".hermes" / "legacy_optical_noir_review_assets_ai"
LOGO = Path("C:/Users/mathi/OneDrive/Desktop/Legacy/Logos sin fondo/Logo Blanco.png")
REPORT_HTML = OUT / "Legacy_Optical_Noir_Campaign_Report.html"
REPORT_PDF = OUT / "Legacy_Optical_Noir_Campaign_Report.pdf"
MANIFEST = OUT / "manifest.json"

CAPTIONS = [
    "NOIR has arrived.\n\nPrecision frames, deep lenses, and a city-after-dark attitude — built for people who prefer their essentials sharp, quiet, and unmistakable.\n\nDiscover the new Legacy Optical Noir edit.\n\n#LegacyEffect #Noir #OpticalDesign #Eyewear #PremiumEyewear",
    "The quietest pieces usually say the most.\n\nNoir brings polished silhouettes, deep lenses, and an after-hours mood to everyday eyewear.\n\nAvailable for review now at Legacy Optical.\n\n#LegacyEffect #Noir #OpticalDesign #Sunglasses",
    "Built for contrast. Designed for restraint.\n\nThe Noir edit pairs clean geometry with premium tones for a look that works from daylight to late night.\n\n#LegacyEffect #Noir #EyewearEdit #PremiumEyewear",
    "Rain, reflections, late plans.\n\nNoir is the pair you reach for when the outfit is simple and the details have to carry it.\n\n#LegacyEffect #Noir #OpticalDesign #CDMXStyle",
    "Four ways into Noir.\n\nEach frame keeps the same brief: refined, wearable, and sharp without shouting.\n\nSave this post and ask Legacy for available models.\n\n#LegacyEffect #Noir #Eyewear #Sunglasses",
    "Your essentials, darker and sharper.\n\nNoir closes the launch sequence with a clean hero frame: minimal, premium, ready for daily rotation.\n\n#LegacyEffect #Noir #PremiumEyewear #OpticalDesign",
]

REPLIES = [
    ("Availability", "Yes — tell us which Noir frame caught your eye and we’ll confirm the closest available model/color."),
    ("Price / range", "They’re premium pieces. Send us the model you liked and we’ll share the current price plus one alternative in the same mood."),
    ("Try-on / visit", "Absolutely. We can help you pick two options before you visit so the selection is faster and more personal."),
    ("Hold / reserve", "We can hold the option once availability is confirmed. Want us to check this frame or send two similar picks?"),
]

SCHEDULE_START = datetime(2026, 6, 20, 11, 30)
SCHEDULE_OFFSETS = [0, 2, 4, 6, 8, 10]
TIMES = [(11, 30), (19, 15), (12, 0), (20, 0), (11, 45), (18, 30)]


def to_data_uri(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    ext = "jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "png"
    return f"data:image/{ext};base64,{data}"


def branded_image(src: Path, index: int) -> Path:
    out = ASSETS / f"legacy_noir_post_{index:02d}_branded.jpg"
    img = Image.open(src).convert("RGBA")
    logo = Image.open(LOGO).convert("RGBA")
    logo = logo.crop(logo.getbbox())
    target_w = int(img.width * 0.25)
    logo = logo.resize((target_w, int(logo.height * target_w / logo.width)), Image.Resampling.LANCZOS)
    logo.putalpha(logo.getchannel("A").point(lambda a: int(a * 0.95)))
    pos = ((img.width - logo.width) // 2, int(img.height * 0.055))
    pad = 28
    halo = Image.new("RGBA", (logo.width + pad * 2, logo.height + pad * 2), (0, 0, 0, 0))
    mask = Image.new("L", halo.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, halo.width, halo.height), radius=32, fill=95)
    mask = mask.filter(ImageFilter.GaussianBlur(16))
    halo.putalpha(mask)
    img.alpha_composite(halo, (pos[0] - pad, pos[1] - pad))
    shadow = Image.new("RGBA", logo.size, (0, 0, 0, 0))
    shadow.putalpha(logo.getchannel("A").point(lambda a: int(a * 0.45)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(3))
    img.alpha_composite(shadow, (pos[0] + 2, pos[1] + 2))
    img.alpha_composite(logo, pos)
    img.convert("RGB").save(out, "JPEG", quality=94, optimize=True, progressive=True)
    return out


def post_date(i: int) -> datetime:
    d = SCHEDULE_START + timedelta(days=SCHEDULE_OFFSETS[i])
    h, m = TIMES[i]
    return d.replace(hour=h, minute=m)


sources = [SRC_DIR / f"legacy_optical_noir_post_{i:02d}.png" for i in range(1, 7)]
post_03_replacement = OUT / "replacement_assets" / "legacy_optical_noir_post_03_replacement_raw.png"
if post_03_replacement.exists():
    sources[2] = post_03_replacement
for src in sources:
    if not src.exists():
        raise FileNotFoundError(src)
if not LOGO.exists():
    raise FileNotFoundError(LOGO)

branded = [branded_image(src, i) for i, src in enumerate(sources, 1)]
logo_uri = to_data_uri(LOGO)

cards = []
for i, img_path in enumerate(branded):
    dt = post_date(i)
    cards.append({
        "title": f"Post {i + 1:02d}",
        "image": to_data_uri(img_path),
        "date": dt.strftime("%a %d %b %Y"),
        "time": dt.strftime("%H:%M"),
        "channels": "Instagram feed",
        "caption": CAPTIONS[i],
    })

post_cards_html = "\n".join(
    f"""
    <article class="post-card">
      <div class="post-img-wrap"><img src="{card['image']}" alt="{escape(card['title'])} image"></div>
      <div class="post-meta">
        <p class="eyebrow">{escape(card['title'])}</p>
        <h3>{escape(card['date'])} · {escape(card['time'])}</h3>
        <div class="pill-row"><span>{escape(card['channels'])}</span><span>Organic</span><span>Logo included</span></div>
        <p class="caption">{escape(card['caption']).replace(chr(10), '<br>')}</p>
      </div>
    </article>
    """
    for card in cards
)

reply_rows = "\n".join(
    f"<div class='reply'><strong>{escape(title)}</strong><p>{escape(body)}</p></div>" for title, body in REPLIES
)

html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Legacy Optical Noir — Campaign Report</title>
<style>
:root {{
  color-scheme: dark;
  --bg: #060504;
  --panel: #15110e;
  --panel2: #0f1714;
  --ink: #f7ecd6;
  --muted: #cab99d;
  --dim: #8f7b62;
  --line: #b07a3c66;
  --accent: #d79a45;
  --green: #123f38;
}}
* {{ box-sizing: border-box; }}
body {{
  margin:0;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  background:
    radial-gradient(circle at 20% 0%, #2a1b10 0, transparent 34%),
    radial-gradient(circle at 90% 10%, #123f38 0, transparent 30%),
    linear-gradient(180deg, #070605, #020202 80%);
  color: var(--ink);
  line-height: 1.52;
}}
main {{ max-width: 1120px; margin: 0 auto; padding: 46px 36px 72px; }}
.hero {{
  position: relative;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 30px;
  padding: 38px;
  min-height: 330px;
  background:
    linear-gradient(135deg, #19110c 0%, #070605 52%, #102b25 100%);
  box-shadow: 0 24px 90px #0009;
}}
.hero:after {{
  content:""; position:absolute; inset:0;
  background: linear-gradient(90deg, #0000 0%, #0000 45%, #0007 100%), url("{cards[3]['image']}") right center / 50% auto no-repeat;
  opacity: .42;
}}
.hero-content {{ position: relative; z-index: 1; max-width: 640px; }}
.logo {{ width: 230px; height:auto; margin-bottom: 28px; filter: drop-shadow(0 10px 20px #000); }}
.eyebrow {{ letter-spacing: .14em; text-transform: uppercase; color: var(--accent); font-size: 11px; font-weight: 800; margin: 0 0 8px; }}
h1 {{ font-size: 46px; line-height: 1.02; margin: 0 0 16px; letter-spacing: -0.045em; }}
h2 {{ font-size: 25px; margin: 0 0 14px; color: #ffe2b8; letter-spacing: -0.025em; }}
h3 {{ margin: 0 0 10px; font-size: 17px; color: #ffe2b8; }}
.dek {{ color: var(--muted); font-size: 17px; max-width: 670px; margin: 0; }}
.section {{ margin-top: 22px; border:1px solid var(--line); border-radius: 24px; padding: 26px; background: color-mix(in srgb, var(--panel) 88%, #000); box-shadow: 0 18px 60px #0005; }}
.grid-2 {{ display:grid; grid-template-columns: 1.1fr .9fr; gap: 18px; }}
.grid-3 {{ display:grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 16px; }}
.metric {{ border:1px solid #d79a4540; background: #090806; border-radius: 18px; padding: 16px; }}
.metric b {{ display:block; font-size: 24px; color: #fff0cf; }}
.metric span {{ color: var(--muted); font-size: 13px; }}
.timeline {{ display:flex; flex-direction:column; gap: 10px; margin-top: 14px; }}
.step {{ display:grid; grid-template-columns: 92px 1fr; gap:14px; padding: 13px 0; border-top:1px solid #d79a4526; }}
.step:first-child {{ border-top:0; }}
.step time {{ color: var(--accent); font-weight:800; font-size: 12px; text-transform: uppercase; letter-spacing:.08em; }}
.phase-note {{ border-left: 3px solid var(--accent); padding: 12px 14px; background:#0005; border-radius: 12px; color: var(--muted); }}
.post-grid {{ display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 18px; margin-top: 16px; }}
.post-card {{ border:1px solid #d79a454d; border-radius: 22px; overflow:hidden; background:#090806; break-inside: avoid; }}
.post-img-wrap {{ background:#000; }}
.post-card img {{ width:100%; aspect-ratio: 1 / 1; object-fit:cover; display:block; }}
.post-meta {{ padding: 18px; }}
.pill-row {{ display:flex; flex-wrap:wrap; gap: 7px; margin: 11px 0 13px; }}
.pill-row span {{ border:1px solid #d79a4555; background:#d79a4512; color:#f5d3a3; border-radius: 999px; padding: 5px 9px; font-size: 11px; font-weight: 700; }}
.caption {{ color: var(--muted); font-size: 13px; margin:0; }}
.reply-grid {{ display:grid; grid-template-columns: repeat(2,1fr); gap: 14px; margin-top: 14px; }}
.reply {{ border:1px solid #d79a453d; background:#080706; border-radius:16px; padding:15px; }}
.reply strong {{ color:#ffe2b8; }}
.reply p {{ margin: 6px 0 0; color: var(--muted); }}
ul {{ margin: 10px 0 0; padding-left: 20px; color: var(--muted); }}
li {{ margin: 6px 0; }}
.footer {{ margin-top:22px; color: var(--dim); font-size: 12px; text-align:center; }}
@page {{ size: Letter; margin: 0; }}
@media print {{
  * {{ -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }}
  body {{ background:#060504 !important; }}
  main {{ max-width:none; width:100%; padding: 28px 24px 34px; }}
  .hero {{ border-radius:20px; padding: 26px; min-height: 260px; break-inside: avoid; }}
  .logo {{ width: 178px; margin-bottom: 16px; }}
  h1 {{ font-size: 34px; }}
  h2 {{ font-size: 20px; }}
  .dek {{ font-size: 13px; }}
  .section {{ padding: 18px; border-radius: 18px; break-inside: avoid; margin-top: 14px; }}
  .posts-section {{ break-before: page; }}
  .post-grid {{ gap: 12px; }}
  .post-meta {{ padding: 12px; }}
  .caption {{ font-size: 10.5px; line-height: 1.38; }}
  .pill-row span {{ font-size: 9px; padding: 4px 7px; }}
  .reply-grid {{ gap: 10px; }}
}}
</style>
</head>
<body><main>
  <header class="hero">
    <div class="hero-content">
      <img class="logo" src="{logo_uri}" alt="Legacy logo">
      <p class="eyebrow">Campaign report · phase 1 organic launch</p>
      <h1>Legacy Optical Noir</h1>
      <p class="dek">A premium, approval-ready campaign plan for launching the Noir visual territory through organic Instagram posts, branded assets, reply scripts, and success criteria before any paid media spend.</p>
    </div>
  </header>

  <section class="section grid-2">
    <div>
      <p class="eyebrow">01 · Campaign summary</p>
      <h2>Why and how this campaign is planned</h2>
      <p>Legacy Noir is designed as a low-friction social launch: premium product visuals first, simple captions, fast reply handling, and clear daily checks. The campaign builds demand before paid ads by proving which frames, messages, and visual angles generate saves, replies, profile visits, and sales conversations.</p>
      <p class="phase-note"><strong>Scope:</strong> Phase 1 covers organic Instagram publishing, client-facing post assets, captions, basic reply scripts, and manual performance evaluation. Paid ads are intentionally out of scope and reserved for Phase 2, where revenue from Phase 1 can be reinvested into tested winners.</p>
    </div>
    <div>
      <p class="eyebrow">High-level timeline</p>
      <div class="timeline">
        <div class="step"><time>Day 0</time><div><strong>Approve</strong><br><span>Client approves image set, logo treatment, captions, and posting window.</span></div></div>
        <div class="step"><time>Days 1–10</time><div><strong>Publish</strong><br><span>Six Instagram feed posts go live across alternating day/time windows.</span></div></div>
        <div class="step"><time>Daily</time><div><strong>Respond</strong><br><span>DMs and comments use short scripts designed to move interest into model selection.</span></div></div>
        <div class="step"><time>Day 11</time><div><strong>Evaluate</strong><br><span>Review saves, replies, profile actions, inquiries, holds, and sales conversations.</span></div></div>
      </div>
    </div>
  </section>

  <section class="section posts-section">
    <p class="eyebrow">02 · Posts and ads</p>
    <h2>Planned posts</h2>
    <p class="phase-note"><strong>Ads:</strong> not included in Legacy Phase 1. Paid ads are reserved for Phase 2 after the organic posts identify the best-performing creative and revenue from Phase 1 can be reinvested into ads.</p>
    <div class="grid-3">
      <div class="metric"><b>6</b><span>organic feed posts</span></div>
      <div class="metric"><b>Instagram</b><span>only channel for this first run</span></div>
      <div class="metric"><b>Phase 2</b><span>ads after proof and reinvestment</span></div>
    </div>
    <div class="post-grid">{post_cards_html}</div>
  </section>

  <section class="section">
    <p class="eyebrow">03 · Messages and replies</p>
    <h2>Response scripts for comments and DMs</h2>
    <p>The reply system keeps the brand premium but operational: acknowledge the signal, confirm availability, offer a narrow next step, and move the prospect toward a model/color choice or visit.</p>
    <div class="reply-grid">{reply_rows}</div>
  </section>

  <section class="section">
    <p class="eyebrow">04 · Campaign evaluation</p>
    <h2>Success criteria and decision gates</h2>
    <div class="grid-2">
      <div>
        <h3>Primary signals</h3>
        <ul>
          <li>Qualified DMs or comments asking for model, price, availability, or visit.</li>
          <li>Post saves and shares indicating style intent beyond passive likes.</li>
          <li>Profile visits and link/profile actions during the posting window.</li>
          <li>Holds, visits, or sales conversations attributed to Noir posts.</li>
        </ul>
      </div>
      <div>
        <h3>Phase 2 readiness</h3>
        <ul>
          <li>Select the top 1–2 organic posts by saves, replies, and commercial intent.</li>
          <li>Confirm which caption angle produced the strongest buyer conversation.</li>
          <li>Only reinvest into ads once organic winners and available inventory are clear.</li>
          <li>Document proof: post URLs, screenshots, metrics, replies, and next action.</li>
        </ul>
      </div>
    </div>
  </section>

  <p class="footer">Prepared for Legacy · first-run campaign report · generated from approved Noir assets with Legacy logo included in every post image.</p>
</main></body></html>
"""

REPORT_HTML.write_text(html, encoding="utf-8")

script = OUT / "render_pdf.mjs"
frontend_package = ROOT.parent / "frontend" / "package.json"
script.write_text(textwrap.dedent(f"""
    import {{ createRequire }} from 'module';
    const require = createRequire('{frontend_package.as_posix()}');
    const {{ chromium }} = require('playwright');
    const browser = await chromium.launch({{ args: ['--no-sandbox', '--disable-dev-shm-usage'] }});
    const page = await browser.newPage({{ viewport: {{ width: 1120, height: 1400 }}, deviceScaleFactor: 1 }});
    await page.goto('file:///{REPORT_HTML.as_posix()}', {{ waitUntil: 'networkidle' }});
    await page.emulateMedia({{ media: 'print' }});
    await page.pdf({{ path: '{REPORT_PDF.as_posix()}', format: 'Letter', printBackground: true, preferCSSPageSize: true }});
    await browser.close();
"""), encoding="utf-8")

subprocess.run(["node", str(script)], check=True)

MANIFEST.write_text(json.dumps({
    "title": "Legacy Optical Noir Campaign Report",
    "html": str(REPORT_HTML),
    "pdf": str(REPORT_PDF),
    "assets": [str(p) for p in branded],
    "logo": str(LOGO),
    "sections": ["Campaign summary", "Posts and ads", "Messages and replies", "Campaign evaluation"],
}, indent=2), encoding="utf-8")

print(json.dumps({"html": str(REPORT_HTML), "pdf": str(REPORT_PDF), "pdf_bytes": REPORT_PDF.stat().st_size, "assets": len(branded)}, indent=2))
