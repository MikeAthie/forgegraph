#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT.parent / '.env'
SCHEDULE = ROOT / '.hermes' / 'legacy_optical_noir_autopublish' / 'schedule.json'
OUT = ROOT / '.hermes' / 'legacy_optical_noir_autopublish' / 'delete_unauthorized_post3_receipt.json'
POST_NUM = 3

def load_env():
    d={}
    for raw in ENV_PATH.read_text(encoding='utf-8', errors='ignore').splitlines():
        if '=' in raw and not raw.lstrip().startswith('#'):
            k,v=raw.split('=',1); d[k.strip()]=v.strip().strip('"').strip("'")
    return d

def graph(method, base, ver, path, token, params=None):
    params=dict(params or {}); params['access_token']=token
    url=f'{base.rstrip("/")}/{ver.strip("/")}/{path.lstrip("/")}'
    data=None
    if method == 'GET':
        url += '?' + urllib.parse.urlencode(params)
    else:
        data=urllib.parse.urlencode(params).encode('utf-8')
    req=urllib.request.Request(url, data=data, method=method, headers={'Accept':'application/json','User-Agent':'forgegraph-emergency-delete/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            status=int(getattr(r,'status',200)); body=r.read(1024*1024)
    except urllib.error.HTTPError as e:
        status=int(e.code); body=e.read(1024*1024)
    try: parsed=json.loads(body.decode('utf-8'))
    except Exception: parsed={'_non_json':body[:500].decode('utf-8', errors='replace')}
    return status, parsed

def safe_error(p):
    e=p.get('error') if isinstance(p,dict) else None
    if isinstance(e,dict):
        return {k:str(e.get(k,''))[:500] for k in ['type','code','error_subcode','message']}
    return p

env=load_env(); schedule=json.loads(SCHEDULE.read_text(encoding='utf-8'))
post=next((p for p in schedule.get('posts',[]) if int(p.get('post',0))==POST_NUM), {})
media_id=str(post.get('provider_media_id') or '')
base=env.get('META_GRAPH_API_BASE_URL','https://graph.facebook.com')
ver=env.get('META_GRAPH_API_VERSION','v24.0')
token=env.get('META_GRAPH_PAGE_ACCESS_TOKEN') or env.get('META_GRAPH_ACCESS_TOKEN')
receipt={'created_at':datetime.now(timezone.utc).isoformat(),'post':POST_NUM,'media_id':media_id,'permalink':post.get('provider_permalink'),'secrets_redacted':True}
if not media_id:
    receipt.update({'ok':False,'blocked':'media_id_missing'})
else:
    before_status,before=graph('GET',base,ver,media_id,token,{'fields':'id,permalink,caption,timestamp,media_type,username'})
    del_status,deleted=graph('DELETE',base,ver,media_id,token,{})
    after_status,after=graph('GET',base,ver,media_id,token,{'fields':'id,permalink'})
    receipt.update({
        'before_status':before_status,
        'before_exists': before_status < 300 and 'error' not in before,
        'delete_status':del_status,
        'delete_response': deleted if del_status < 300 else safe_error(deleted),
        'after_status':after_status,
        'after_error': safe_error(after) if after_status >=300 or 'error' in after else None,
        'ok': del_status < 300 and bool(deleted.get('success', deleted.get('id', True))) and (after_status >= 300 or 'error' in after),
    })
OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps(receipt, indent=2, ensure_ascii=False))
