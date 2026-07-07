from infrastructure.orm.models import Graph, CompanyOpportunity, ServiceDeliverable

ids = [
    'f950d3ae-ca93-41a3-9d00-0ca3e12e3f50',
    'adb1d074-1033-40ef-a8df-58afaa6bb60e',
    '3fe9d5b3-9773-4130-886f-ac5a5388b21b',
    '0a19ee22-acf2-4808-9a9d-ff6bb8ade47c',
    '7fe6bc22-2ea9-4f7f-8bea-9065714abcff',
]
for gid in ids:
    g = Graph.objects.get(id=gid)
    types = list(ServiceDeliverable.objects.filter(company=g).values_list('deliverable_type', flat=True))
    print(gid, g.name, 'opps', CompanyOpportunity.objects.filter(company=g).count(), 'deliverables', len(types), sorted(set(types)))
    for opp in CompanyOpportunity.objects.filter(company=g).order_by('created_at'):
        career_ops = (opp.metadata_json or {}).get('career_ops', {})
        print('  -', opp.id, opp.title, career_ops.get('employer_name'), career_ops.get('application_status'))
