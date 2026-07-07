#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(r'C:\Users\mathi\AppData\Local\hermes\scripts\legacy_optical_noir_autopublish.py')
spec = importlib.util.spec_from_file_location('legacy_autopublish', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)  # type: ignore[union-attr]

schedule = json.loads(Path('.hermes/legacy_optical_noir_autopublish/schedule.json').read_text(encoding='utf-8'))
post = schedule['posts'][0]
asset_path = Path(post['asset_path'])
asset_hash = mod.file_sha256(asset_path)
valid = mod.validate_backend_approval(post, asset_hash)
missing = mod.validate_backend_approval({**post, 'idempotency_key': 'missing-draft-for-guardrail-test'}, asset_hash)
wrong_hash = mod.validate_backend_approval(post, '0' * 64)
print(json.dumps({
    'valid_replacement_approved': valid,
    'missing_draft_rejected': missing,
    'wrong_hash_rejected': wrong_hash,
    'pass': valid.get('ok') is True and missing.get('ok') is False and wrong_hash.get('ok') is False,
}, indent=2, ensure_ascii=False))
if not (valid.get('ok') is True and missing.get('ok') is False and wrong_hash.get('ok') is False):
    raise SystemExit(1)
