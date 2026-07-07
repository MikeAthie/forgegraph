import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

work = Path('.hermes/instagram_noir_launch_preview')
caption_path = work / 'legacy_noir_launch_caption.txt'
receipt_path = work / 'instagram_publish_receipt.json'
public_url = 'https://66e4-189-203-252-96.ngrok-free.app/legacy_noir_launch_feed_01_with_legacy_logo_v2.jpg'
local_image_path = work / 'legacy_noir_launch_feed_01_with_legacy_logo_v2.jpg'

load_dotenv(Path('..') / '.env', override=False)
user_token = (os.environ.get('META_GRAPH_ACCESS_TOKEN') or os.environ.get('INSTAGRAM_GRAPH_API') or '').strip()
version = (os.environ.get('META_GRAPH_API_VERSION') or 'v24.0').strip()
ig_id = (os.environ.get('META_GRAPH_IG_USER_ID_ALLOWLIST') or '17841456942553235').split(',')[0].strip()
caption = caption_path.read_text(encoding='utf-8')
base = f'https://graph.facebook.com/{version}'

if not user_token or user_token.startswith('CHANGE_ME'):
    raise SystemExit('NO_VALID_TOKEN')


def graph_get(path: str, params: dict, token: str):
    payload = dict(params)
    payload['access_token'] = token
    response = requests.get(base + path, params=payload, timeout=45)
    try:
        data = response.json()
    except Exception:
        data = {'_non_json': response.text[:500]}
    return response, data


def graph_post(path: str, data: dict, token: str):
    payload = dict(data)
    payload['access_token'] = token
    response = requests.post(base + path, data=payload, timeout=90)
    try:
        parsed = response.json()
    except Exception:
        parsed = {'_non_json': response.text[:500]}
    return response, parsed


def fail_with_graph_error(prefix: str, payload: dict):
    error = payload.get('error') if isinstance(payload, dict) else None
    if error:
        print(prefix + '_ERROR_TYPE=' + str(error.get('type')))
        print(prefix + '_ERROR_CODE=' + str(error.get('code')))
        print(prefix + '_ERROR_SUBCODE=' + str(error.get('error_subcode')))
        print(prefix + '_ERROR_MESSAGE=' + str(error.get('message'))[:1200])
    else:
        print(prefix + '_PAYLOAD=' + json.dumps(payload, ensure_ascii=False, sort_keys=True)[:1200])


# Resolve Page access token for the Page linked to the target IG account. Never print token values.
response, pages = graph_get('/me/accounts', {'fields': 'id,name,access_token,instagram_business_account'}, user_token)
if response.status_code >= 300 or 'error' in pages:
    fail_with_graph_error('PAGES', pages)
    raise SystemExit(1)
page_token = None
page_id = None
page_name = None
for page in pages.get('data', []):
    if str((page.get('instagram_business_account') or {}).get('id')) == str(ig_id):
        page_token = page.get('access_token')
        page_id = page.get('id')
        page_name = page.get('name')
        break
publish_token = page_token or user_token
print('SELECTED_PAGE_ID=' + str(page_id))
print('SELECTED_PAGE_NAME=' + str(page_name))
print('USING_PAGE_TOKEN=***' + ('yes' if page_token else 'no'))

# Verify public image fetchability without special headers; Meta must be able to fetch this URL.
verify = requests.get(public_url, stream=True, timeout=45)
print('PUBLIC_IMAGE_STATUS=' + str(verify.status_code))
print('PUBLIC_IMAGE_CONTENT_TYPE=' + str(verify.headers.get('content-type')))
print('PUBLIC_IMAGE_CONTENT_LENGTH=' + str(verify.headers.get('content-length')))
verify.close()
if verify.status_code >= 300 or 'image' not in str(verify.headers.get('content-type', '')).lower():
    raise SystemExit('PUBLIC_IMAGE_NOT_FETCHABLE')

response, ig_before = graph_get(f'/{ig_id}', {'fields': 'id,username,media_count'}, publish_token)
if response.status_code >= 300 or 'error' in ig_before:
    fail_with_graph_error('IG_BEFORE', ig_before)
    raise SystemExit(1)
print('IG_USERNAME=' + str(ig_before.get('username')))
print('IG_MEDIA_COUNT_BEFORE=' + str(ig_before.get('media_count')))

# Create Instagram media container for feed image.
response, created = graph_post(f'/{ig_id}/media', {'image_url': public_url, 'caption': caption}, publish_token)
print('CREATE_CONTAINER_STATUS=' + str(response.status_code))
if response.status_code >= 300 or 'error' in created:
    fail_with_graph_error('CREATE_CONTAINER', created)
    raise SystemExit(1)
creation_id = created.get('id')
print('CREATION_ID=' + str(creation_id))
if not creation_id:
    raise SystemExit('NO_CREATION_ID')

status_payload = None
for attempt in range(1, 13):
    time.sleep(2 if attempt == 1 else 5)
    response, status_payload = graph_get(f'/{creation_id}', {'fields': 'id,status_code,status'}, publish_token)
    status_code = status_payload.get('status_code') if isinstance(status_payload, dict) else None
    print(f'CONTAINER_POLL_{attempt}_HTTP={response.status_code}_STATUS_CODE={status_code}')
    if response.status_code >= 300 or 'error' in status_payload:
        fail_with_graph_error('CONTAINER_STATUS', status_payload)
        raise SystemExit(1)
    if status_code == 'FINISHED':
        break
    if status_code == 'ERROR':
        print('CONTAINER_STATUS_PAYLOAD=' + json.dumps(status_payload, ensure_ascii=False, sort_keys=True)[:1200])
        raise SystemExit(1)
else:
    raise SystemExit('CONTAINER_NOT_READY')

# Publish container.
response, published = graph_post(f'/{ig_id}/media_publish', {'creation_id': creation_id}, publish_token)
print('PUBLISH_STATUS=' + str(response.status_code))
if response.status_code >= 300 or 'error' in published:
    fail_with_graph_error('PUBLISH', published)
    raise SystemExit(1)
media_id = published.get('id')
print('PUBLISHED_MEDIA_ID=' + str(media_id))
if not media_id:
    raise SystemExit('NO_MEDIA_ID')

# Fetch receipt/permalink. If immediately unavailable, retry briefly.
media = None
for attempt in range(1, 6):
    time.sleep(3)
    response, media = graph_get(f'/{media_id}', {'fields': 'id,permalink,media_type,caption,timestamp,username'}, publish_token)
    print(f'MEDIA_RECEIPT_ATTEMPT_{attempt}_STATUS=' + str(response.status_code))
    if response.status_code < 300 and 'error' not in media:
        break
    fail_with_graph_error('MEDIA_RECEIPT', media)
else:
    media = {'id': media_id, 'receipt_read_error': media}

receipt = {
    'published': True,
    'graph_version': version,
    'ig_id': ig_id,
    'ig_username': ig_before.get('username'),
    'page_id': page_id,
    'page_name': page_name,
    'used_page_token': bool(page_token),
    'public_image_url': public_url,
    'local_image_path': str(local_image_path),
    'caption': caption,
    'creation_id': creation_id,
    'container_status': status_payload,
    'media_id': media_id,
    'media': media,
    'published_at_epoch': time.time(),
}
receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding='utf-8')
print('PERMALINK=' + str(media.get('permalink') if isinstance(media, dict) else None))
print('RECEIPT_PATH=' + str(receipt_path))
