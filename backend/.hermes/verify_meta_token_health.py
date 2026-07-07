#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT.parent / '.env'
OUT = ROOT / '.hermes' / 'legacy_optical_noir_autopublish' / 'meta_token_health_latest.json'

def env():
    d={}
    for raw in ENV_PATH.read_text(encoding='utf-8', errors='ignore').splitlines():
        if '=' in raw and not raw.lstrip().startswith('#'):
            k,v=raw.split('=',1); d[k.strip()]=v.strip().strip('"').strip("'")
    return d

def get(url, params):
    full=url+'?'+urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(full, headers={'Accept':'application/json'}), timeout=45) as r:
        return int(getattr(r,'status',200)), json.loads(r.read().decode('utf-8'))

e=env(); base=e.get('META_GRAPH_API_BASE_URL','https://graph.facebook.com').rstrip('/'); ver=e.get('META_GRAPH_API_VERSION','v24.0').strip('/')
app_token=f"{e['META_GRAPH_APP_ID']}|{e['META_GRAPH_APP_SECRET']}"
status, debug = get(f'{base}/{ver}/debug_token', {'input_token': e['META_GRAPH_ACCESS_TOKEN'], 'access_token': app_token})
page_token=e.get('META_GRAPH_PAGE_ACCESS_TOKEN') or e.get('META_GRAPH_ACCESS_TOKEN')
ig=e.get('META_GRAPH_IG_USER_ID_ALLOWLIST','').split(',')[0].strip()
status2, ig_data = get(f'{base}/{ver}/{ig}', {'fields':'id,username,media_count', 'access_token': page_token})
payload={
 'checked_at': datetime.now(timezone.utc).isoformat(),
 'debug_status': status,
 'token': {k:debug.get('data',{}).get(k) for k in ['app_id','type','application','data_access_expires_at','expires_at','is_valid','scopes','user_id']},
 'ig_status': status2,
 'instagram': {k:ig_data.get(k) for k in ['id','username','media_count']},
 'secrets_redacted': True,
}
OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
print(json.dumps(payload, indent=2))
