from pathlib import Path
import json, hashlib, zipfile
from datetime import datetime, timezone

run_dir = Path('C:/Users/mathi/projects/forgegraph/.hermes/legacy_client_delivery_v2_20260609')
deliv = run_dir / 'deliverables'
assets = run_dir / 'assets'
client_dir = run_dir / 'client_package'
(client_dir / 'deliverables').mkdir(parents=True, exist_ok=True)
(client_dir / 'assets').mkdir(parents=True, exist_ok=True)

def copy(src: Path, dst: Path):
    dst.write_bytes(src.read_bytes())

for name in ['Legacy_Optical_Noir_Entrega_Inicial.pdf', 'Legacy_Optical_Noir_Entrega_Inicial.html']:
    copy(deliv / name, client_dir / 'deliverables' / name)
for p in sorted(assets.glob('legacy_optical_noir_post_*.png')):
    copy(p, client_dir / 'assets' / p.name)

def sha256(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

files=[]
for p in sorted(client_dir.rglob('*')):
    if p.is_file():
        files.append({'path': str(p.relative_to(client_dir)).replace('\\','/'), 'bytes': p.stat().st_size, 'sha256': sha256(p)})
manifest = {
    'schema': 'forgegraph.client_delivery_package.v2',
    'client': 'Legacy',
    'campaign': 'Optical Noir',
    'created_at': datetime.now(timezone.utc).isoformat(),
    'deliverables': [
        'Account brief / context pack',
        'Strategy brief',
        'Message house / brand-content pack',
        'Channel plan',
        'Creative asset map',
        'Publication-ready drafts/assets',
    ],
    'delivery_constraints': {
        'markdown_files_in_client_package': 0,
        'strategy_created_before_assets': True,
        'assets_policy': 'fresh AI-generated, campaign-aligned visuals; no recycled prior draft assets',
        'whatsapp_policy': 'brief message plus attachment, no long-form deliverables pasted into chat'
    },
    'files': files,
}
manifest_path = client_dir / 'manifest.json'
manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
# rebuild file listing with manifest
files=[]
for p in sorted(client_dir.rglob('*')):
    if p.is_file():
        files.append({'path': str(p.relative_to(client_dir)).replace('\\','/'), 'bytes': p.stat().st_size, 'sha256': sha256(p)})
manifest['files'] = files
manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')

zip_path = run_dir / 'Legacy_Optical_Noir_Entrega_Inicial_CLIENT.zip'
if zip_path.exists(): zip_path.unlink()
with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
    for p in sorted(client_dir.rglob('*')):
        if p.is_file():
            z.write(p, p.relative_to(client_dir))
with zipfile.ZipFile(zip_path) as z:
    names=z.namelist()
    md=[n for n in names if n.lower().endswith('.md') or '/internal_source/' in n]
    required=['deliverables/Legacy_Optical_Noir_Entrega_Inicial.pdf','deliverables/Legacy_Optical_Noir_Entrega_Inicial.html','manifest.json']
    missing=[r for r in required if r not in names]
    asset_count=sum(1 for n in names if n.startswith('assets/legacy_optical_noir_post_') and n.endswith('.png'))
    if md: raise AssertionError(f'Markdown/internal source leaked into client ZIP: {md}')
    if missing: raise AssertionError(f'Missing required files: {missing}')
    if asset_count != 6: raise AssertionError(f'Expected 6 final assets, got {asset_count}')
print(json.dumps({'client_dir': str(client_dir), 'zip_path': str(zip_path), 'zip_bytes': zip_path.stat().st_size, 'zip_sha256': sha256(zip_path), 'file_count': len(names), 'asset_count': asset_count, 'markdown_files_in_zip': len(md)}, indent=2))
