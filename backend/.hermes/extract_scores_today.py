import json
from infrastructure.orm.models import AssetVersion, CompanyOpportunity
ids = [
    ('Remote Talent LATAM / U.S. digital health client', '9c859f4d-5147-4d36-b9c5-0c96f5994bf2', '3cfe02d5-2c5c-441e-8595-41c04176747d'),
    ('South Geeks', '6835fea6-3b63-46f1-9183-48568a26579d', 'cd5cc6f2-7fc4-46ee-afce-fedec58c3575'),
    ('Clipbook', '67a63de1-ded5-4430-8941-45f2ca77fcf1', 'f8c693cc-2d16-4082-aeee-29ba2f9d0021'),
    ('RYZ Labs', '98a61277-cd18-42c6-809d-550603f0321c', 'e2ae7c97-cb44-47a7-b6bd-d43dc15963a8'),
    ('Belvo', '43e9f899-e16d-4723-a963-a86511fd6f5a', '43ed694a-94ab-4f41-b514-53d2d031731c'),
]
rows=[]
for company, ats_id, rec_id in ids:
    ats = AssetVersion.objects.get(id=ats_id).provenance_json['career_ops']
    rec = AssetVersion.objects.get(id=rec_id).provenance_json['career_ops']
    rows.append({
        'company': company,
        'ats_score': ats.get('atsScore'),
        'ats_verdict': ats.get('verdict'),
        'recruiter_score': rec.get('overall_score') or rec.get('score'),
        'recruiter_recommendation': rec.get('recommendation'),
        'recruiter_summary': rec.get('summary') or rec.get('verdict'),
    })
print(json.dumps(rows, indent=2))
