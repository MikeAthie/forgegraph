import base64
import json
import re
from pathlib import Path

from infrastructure.orm.models import AssetVersion

INPUT_PATH = Path('/app/.hermes/career_ops_ats_packets_20260617.json')
OUTPUT_DIR = Path('/app/.hermes/career_ops_final_pdfs')
MANIFEST_PATH = OUTPUT_DIR / 'manifest.json'


def slug(value: str) -> str:
    value = value.replace('—', '-').replace('&', 'and')
    value = re.sub(r'[^A-Za-z0-9]+', '-', value).strip('-').lower()
    return value[:90] or 'career-ops-resume'


payload = json.loads(INPUT_PATH.read_text(encoding='utf-8'))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
exports = []
for index, item in enumerate(payload['results'], start=1):
    pdf_version = AssetVersion.objects.get(id=item['ats_resume_pdf_asset_version_id'])
    parse_version = AssetVersion.objects.get(id=item['ats_resume_parseability_report_asset_version_id'])
    text_version = AssetVersion.objects.get(id=item['ats_resume_text_asset_version_id'])
    pdf_bytes = base64.b64decode(pdf_version.provenance_json['inline_content_base64'])
    text_bytes = base64.b64decode(text_version.provenance_json['inline_content_base64'])
    parse_payload = parse_version.provenance_json['career_ops']
    title = item['opportunity_title']
    filename = f"{index:02d}-{slug(title)}-ats-resume.pdf"
    text_filename = filename.replace('.pdf', '.txt')
    pdf_path = OUTPUT_DIR / filename
    text_path = OUTPUT_DIR / text_filename
    pdf_path.write_bytes(pdf_bytes)
    text_path.write_bytes(text_bytes)
    export = {
        'index': index,
        'opportunity_id': item['opportunity_id'],
        'opportunity_title': title,
        'employer_name': item.get('employer_name'),
        'packet_asset_version_id': item['packet_asset_version_id'],
        'ats_resume_pdf_asset_version_id': item['ats_resume_pdf_asset_version_id'],
        'ats_resume_text_asset_version_id': item['ats_resume_text_asset_version_id'],
        'ats_resume_parseability_report_asset_version_id': item['ats_resume_parseability_report_asset_version_id'],
        'pdf_content_hash': pdf_version.content_hash,
        'pdf_size_bytes': pdf_version.size_bytes,
        'pdf_mime_type': pdf_version.mime_type,
        'parseability_status': parse_payload['status'],
        'parseability_checks': parse_payload['checks'],
        'readiness_status': item['readiness']['status'],
        'readiness_blockers': item['readiness']['blockers'],
        'readiness_checks': item['readiness']['checks'],
        'pdf_path': str(pdf_path),
        'text_path': str(text_path),
    }
    assert pdf_version.mime_type == 'application/pdf'
    assert pdf_bytes.startswith(b'%PDF-')
    assert parse_payload['status'] == 'passed'
    assert item['readiness']['checks']['ats_resume_pdf_present'] == 'pass'
    assert item['readiness']['checks']['ats_resume_pdf_mime_type'] == 'pass'
    assert item['readiness']['checks']['ats_resume_parseability_passed'] == 'pass'
    assert item['readiness']['checks']['exact_version_approval_present'] == 'blocked'
    exports.append(export)
MANIFEST_PATH.write_text(json.dumps({'company_id': payload['company_id'], 'exports': exports}, indent=2, sort_keys=True), encoding='utf-8')
print(json.dumps({'export_count': len(exports), 'output_dir': str(OUTPUT_DIR), 'manifest_path': str(MANIFEST_PATH)}, sort_keys=True))
for export in exports:
    print(export['index'], export['opportunity_title'], export['pdf_path'], export['pdf_content_hash'], export['readiness_blockers'])
