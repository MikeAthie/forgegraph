from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, 'C:/Users/mathi/projects/forgegraph/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from django.utils import timezone
from infrastructure.orm.models import (
    CommunicationEventReceipt,
    CommunicationMessage,
    CompanySignal,
    ServiceEngagement,
    StateProjection,
)

RUN_ID = 'legacy_forgegraph_native_v1_20260609_1710'
BASE = Path('C:/Users/mathi/projects/forgegraph/.hermes/legacy_forgegraph_native_run')
PHASE2 = json.loads((BASE / 'phase2_package_result.json').read_text(encoding='utf-8'))
TEXT_MESSAGE_ID = '3EB0DF3E93EF860C153BD1'
MEDIA_MESSAGE_ID = '3EB0A9CC81B962BA19040B'
CHAT_ID = '5215539003599@c.us'

engagement = ServiceEngagement.objects.select_related('organization','company','requested_by').get(id='201201f2-9f69-40c1-ad59-552a041d64c5')
org, company, user = engagement.organization, engagement.company, engagement.requested_by
msg = CommunicationMessage.objects.get(id=PHASE2['planned_message_id'])
meta = dict(msg.metadata_json or {})
meta.update({
    'send_status': 'sent',
    'sent_at': timezone.now().isoformat(),
    'target_chat_id': CHAT_ID,
    'whatsapp_text_message_id': TEXT_MESSAGE_ID,
    'whatsapp_media_message_id': MEDIA_MESSAGE_ID,
    'zip_sha256': PHASE2['zip_sha256'],
})
msg.metadata_json = meta
msg.save(update_fields=['metadata_json','updated_at'])

receipt, _ = CommunicationEventReceipt.objects.update_or_create(
    consumer_group='atlas_whatsapp_delivery',
    idempotency_key=f'{RUN_ID}:mike:whatsapp-media:{MEDIA_MESSAGE_ID}',
    defaults={
        'event_id': MEDIA_MESSAGE_ID,
        'topic': 'local.whatsapp.send-media',
        'organization': org,
        'company': company,
        'event_type': 'whatsapp.media.sent',
        'schema_version': 'local.whatsapp.v1',
        'aggregate_type': 'service_engagement',
        'aggregate_id': str(engagement.id),
        'status': 'handled',
        'payload_json': {
            'source': RUN_ID,
            'chatId': CHAT_ID,
            'textMessageId': TEXT_MESSAGE_ID,
            'mediaMessageId': MEDIA_MESSAGE_ID,
            'filePath': PHASE2['zip_path'],
            'fileName': 'Legacy_Optical_Noir_FG_NATIVE_CLIENT.zip',
            'sha256': PHASE2['zip_sha256'],
            'package_asset_id': PHASE2['package_asset_id'],
            'package_deliverable_id': PHASE2['package_deliverable_id'],
        },
        'handled_at': timezone.now(),
    },
)
CompanySignal.objects.update_or_create(
    company=company,
    source='atlas_whatsapp_delivery',
    external_key=f'{RUN_ID}:mike:sent',
    defaults={
        'organization': org,
        'created_by': user,
        'signal_type': 'manual',
        'signal_kind': 'milestone',
        'domain_context': 'atlas_agency_delivery',
        'status': 'converted',
        'title': 'Legacy package sent to Mike via WhatsApp',
        'summary': 'Client package was sent to Mike, not Toy, through the local WhatsApp bridge and receipt was persisted in ForgeGraph.',
        'channel': 'whatsapp',
        'contact_alias': 'Mike +52 1 55 3900 3599',
        'metadata_json': {
            'source': RUN_ID,
            'chatId': CHAT_ID,
            'textMessageId': TEXT_MESSAGE_ID,
            'mediaMessageId': MEDIA_MESSAGE_ID,
            'communication_event_receipt_id': str(receipt.id),
        },
        'occurred_at': timezone.now(),
    },
)
projection = StateProjection.objects.get(company=company, program_id='c28e3670-da75-40eb-9633-cb85f5d3171a', projection_type='legacy_client_delivery_run_state')
state = dict(projection.json_state or {})
state.update({
    'phase': 'delivered_to_mike_whatsapp',
    'whatsapp_text_message_id': TEXT_MESSAGE_ID,
    'whatsapp_media_message_id': MEDIA_MESSAGE_ID,
    'communication_event_receipt_id': str(receipt.id),
    'delivered_chat_id': CHAT_ID,
})
projection.json_state = state
projection.markdown_summary = 'ForgeGraph-owned package delivered to Mike via WhatsApp; receipt persisted.'
projection.save(update_fields=['json_state','markdown_summary','updated_at'])

out = {
    'phase': 'phase3_receipt_recorded',
    'communication_message_id': str(msg.id),
    'communication_event_receipt_id': str(receipt.id),
    'text_message_id': TEXT_MESSAGE_ID,
    'media_message_id': MEDIA_MESSAGE_ID,
    'chat_id': CHAT_ID,
    'state_projection_id': str(projection.id),
}
(BASE / 'phase3_delivery_receipt.json').write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps(out, indent=2, ensure_ascii=False))
