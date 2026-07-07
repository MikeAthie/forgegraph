import json
from pathlib import Path

from infrastructure.orm.models import DepartmentRegistry, TaskRoutingRecord, WorkWhiteboard, CompanyOpportunity

payload = json.loads(Path('/app/.hermes/career_ops_first_prompt_docker_real.json').read_text(encoding='utf-8'))
wb = WorkWhiteboard.objects.get(id=payload['whiteboard_id'])
tasks = TaskRoutingRecord.objects.filter(id__in=payload['task_ids']).order_by('created_at')
departments = DepartmentRegistry.objects.filter(id__in=payload['department_ids'])
opportunities = CompanyOpportunity.objects.filter(company_id=payload['company_id'])
postings = wb.metadata_json.get('career_ops', {}).get('first_prompt', {}).get('postings', [])
print('whiteboard_status', wb.status)
print('whiteboard_postings', len(postings))
print('kanban_count', tasks.count())
print('kanban_statuses', sorted(tasks.values_list('status', flat=True)))
print('departments', departments.count())
print('opportunities', opportunities.count())
print('first_posting_title', postings[0]['title'] if postings else '')
print('first_posting_location', postings[0]['location'] if postings else '')
