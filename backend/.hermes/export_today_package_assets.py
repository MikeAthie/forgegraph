import json
from infrastructure.orm.models import AssetVersion
ids = {
  'Remote Talent LATAM': {
    'cover_letter': 'a01a91e1-ab6e-4e88-bb9a-678b4fcb5f96',
    'ats': '9c859f4d-5147-4d36-b9c5-0c96f5994bf2',
    'recruiter': '3cfe02d5-2c5c-441e-8595-41c04176747d'
  },
  'South Geeks': {
    'cover_letter': 'e382359f-7189-4ae4-ba61-07e55b9633c5',
    'ats': '6835fea6-3b63-46f1-9183-48568a26579d',
    'recruiter': 'cd5cc6f2-7fc4-46ee-afce-fedec58c3575'
  },
  'Clipbook': {
    'cover_letter': '1471bb1e-a433-4f62-84ba-beff5391f132',
    'ats': '67a63de1-ded5-4430-8941-45f2ca77fcf1',
    'recruiter': 'f8c693cc-2d16-4082-aeee-29ba2f9d0021'
  },
  'RYZ Labs': {
    'cover_letter': '6ba73858-1da2-4108-96df-6c7614178ef8',
    'ats': '98a61277-cd18-42c6-809d-550603f0321c',
    'recruiter': 'e2ae7c97-cb44-47a7-b6bd-d43dc15963a8'
  },
  'Belvo': {
    'cover_letter': 'a0299f3c-8a9a-46ea-9e84-d258c9f9b18f',
    'ats': '43e9f899-e16d-4723-a963-a86511fd6f5a',
    'recruiter': '43ed694a-94ab-4f41-b514-53d2d031731c'
  }
}
out={}
for company, parts in ids.items():
    out[company]={}
    for kind, vid in parts.items():
        version=AssetVersion.objects.get(id=vid)
        out[company][kind]=version.provenance_json.get('career_ops')
print(json.dumps(out, indent=2, sort_keys=True))
