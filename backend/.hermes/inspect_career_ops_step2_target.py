from infrastructure.orm.models import Asset, CompanyOpportunity, Graph

companies = []
for company in Graph.objects.order_by('-created_at')[:20]:
    opp_count = CompanyOpportunity.objects.filter(company=company).count()
    if opp_count:
        companies.append((str(company.id), company.name, str(company.owner_id), opp_count))
print('companies_with_opportunities')
for row in companies[:10]:
    print(row)

company_id = 'f950d3ae-ca93-41a3-9d00-0ca3e12e3f50'
try:
    company = Graph.objects.get(id=company_id)
    print('target_company', company.id, company.name, 'owner', company.owner_id)
    print('target_opportunities', CompanyOpportunity.objects.filter(company=company).count())
    print('base_cv_assets', Asset.objects.filter(company=company, source_key='career_ops:cv_source').count())
    for opp in CompanyOpportunity.objects.filter(company=company).order_by('created_at'):
        co = (opp.metadata_json or {}).get('career_ops', {})
        print('opp', opp.id, opp.title, '|', co.get('employer_name'), '|', co.get('location'), '|', co.get('posting_source_mode'))
except Graph.DoesNotExist:
    print('target_company_missing')
