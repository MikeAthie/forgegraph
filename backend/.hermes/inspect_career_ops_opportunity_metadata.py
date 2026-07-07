from infrastructure.orm.models import CompanyOpportunity
for opp in CompanyOpportunity.objects.filter(company_id='f950d3ae-ca93-41a3-9d00-0ca3e12e3f50').order_by('created_at'):
    print('OPP', opp.id, opp.title)
    print((opp.metadata_json or {}).get('career_ops', {}))
