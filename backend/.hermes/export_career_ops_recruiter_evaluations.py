import json
from pathlib import Path

from infrastructure.orm.models import AssetVersion

INPUT_PATH = Path('/app/.hermes/career_ops_ats_packets_20260617.json')
OUTPUT_PATH = Path('/app/.hermes/career_ops_final_pdfs/recruiter_evaluations.json')
payload = json.loads(INPUT_PATH.read_text(encoding='utf-8'))
reports = []
for index, result in enumerate(payload['results'], start=1):
    version_id = result.get('recruiter_evaluation_asset_version_id')
    if not version_id:
        raise AssertionError(f'missing recruiter evaluation for result {index}')
    version = AssetVersion.objects.get(id=version_id)
    report = version.provenance_json['career_ops']
    reports.append(
        {
            'index': index,
            'opportunity_title': result['opportunity_title'],
            'asset_version_id': version_id,
            'overall_score': report['overall_score'],
            'recommendation': report['recommendation'],
            'scores': report['scores'],
            'strengths': report['strengths'],
            'risks': report['risks'],
            'external_side_effects_allowed': report['external_side_effects_allowed'],
        }
    )
OUTPUT_PATH.write_text(json.dumps({'reports': reports}, indent=2, sort_keys=True), encoding='utf-8')
print(json.dumps({'export_count': len(reports), 'output_path': str(OUTPUT_PATH)}, sort_keys=True))
for report in reports:
    print(report['index'], report['overall_score'], report['recommendation'], report['scores'])
