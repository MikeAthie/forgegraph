import json
from pathlib import Path

from infrastructure.orm.models import CompanyOpportunity, TaskRoutingRecord, WorkWhiteboard

payload = json.loads(Path('/app/.hermes/career_ops_live_discovery_docker_20260617_v3.json').read_text(encoding='utf-8'))
whiteboard = WorkWhiteboard.objects.get(id=payload['whiteboard_id'])
tasks = list(TaskRoutingRecord.objects.filter(id__in=payload['task_ids']).order_by('created_at'))
opportunities = list(CompanyOpportunity.objects.filter(company_id=payload['company_id']).order_by('title'))
first_prompt = whiteboard.metadata_json['career_ops']['first_prompt']
print('whiteboard_source_mode', first_prompt['source_mode'])
print('whiteboard_postings', len(first_prompt['postings']))
print('kanban_titles', [task.metadata_json['title'] for task in tasks])
print('kanban_statuses', [task.status for task in tasks])
print('opportunities', len(opportunities))
print('opportunity_source_modes', sorted({opp.metadata_json['career_ops']['source_mode'] for opp in opportunities}))
print('external_side_effects', sorted({opp.metadata_json['career_ops']['external_side_effects_allowed'] for opp in opportunities}))
