#!/usr/bin/env python3
"""Fix F821: Undefined name `_sys` in reports.py:301.

Root cause: `import sys as _sys_t108` is local to `blast_weekly()` (line 267),
but the inner `_blast_weekly_impl()` references `_sys` at line 301. This is a
pre-existing latent bug — the helper's `print(..., file=_sys.stderr)` would
raise NameError if the idempotency branch is ever hit.

Fix: hoist `import sys` to module level, replace `_sys_t108` with `sys`
inside `blast_weekly()`, and fix the broken `_sys` reference in the helper.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path("/Users/jerrymauri/Flipus")
path = ROOT / "app/api/v1/reports.py"
text = path.read_text(encoding="utf-8")

# 1) Add `import sys` at module level — after the existing line 2 (from datetime...)
#    and before line 4 (from fastapi...). The cleanest slot: line 3, blank.
#    Original:
#      1: """FLIPUS v1.1 ..."""
#      2: from datetime import UTC, datetime
#      3: <blank>
#      4: from fastapi import APIRouter, ...
old = '"""FLIPUS v1.1 — Reports API + WA Blast + Sabat Info."""\nfrom datetime import UTC, datetime\n\nfrom fastapi import APIRouter, Depends, HTTPException, status\n'
new = '"""FLIPUS v1.1 — Reports API + WA Blast + Sabat Info."""\nimport sys\nfrom datetime import UTC, datetime\n\nfrom fastapi import APIRouter, Depends, HTTPException, status\n'
assert old in text, "module header not found verbatim"
text = text.replace(old, new, 1)
print("   added module-level `import sys`")

# 2) Inside blast_weekly() (line 267 originally, now shifted to 268): rename import
old = "    import sys as _sys_t108\n    import traceback as _tb_t108\n    try:\n        return _blast_weekly_impl(request, db, current_user)\n    except HTTPException:\n        raise\n    except Exception as e:\n        tb = _tb_t108.format_exc()\n        print(f\"[DBG blast-500] user={current_user.get('id')} tenant={current_user.get('tenant_id')} idem={request.idempotency_key}\\n{tb}\", file=_sys_t108.stderr, flush=True)\n        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f'Gagal blast WA: {type(e).__name__}: {str(e)[:300]}. Cek backend log untuk traceback lengkap.') from e"
new = "    import traceback as _tb_t108\n    try:\n        return _blast_weekly_impl(request, db, current_user)\n    except HTTPException:\n        raise\n    except Exception as e:\n        tb = _tb_t108.format_exc()\n        print(f\"[DBG blast-500] user={current_user.get('id')} tenant={current_user.get('tenant_id')} idem={request.idempotency_key}\\n{tb}\", file=sys.stderr, flush=True)\n        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f'Gagal blast WA: {type(e).__name__}: {str(e)[:300]}. Cek backend log untuk traceback lengkap.') from e"
assert old in text, "blast_weekly body not found verbatim"
text = text.replace(old, new, 1)
print("   replaced local `_sys_t108` with module-level `sys`")

# 3) Inside _blast_weekly_impl(): fix the broken `_sys.stderr` reference
old = '                f"reusing existing job id={existing.id} status={existing.status}",\n                file=_sys.stderr,\n            )'
new = '                f"reusing existing job id={existing.id} status={existing.status}",\n                file=sys.stderr,\n            )'
assert old in text, "_blast_weekly_impl idempotency print not found"
text = text.replace(old, new, 1)
print("   fixed `_sys.stderr` -> `sys.stderr` in _blast_weekly_impl")

path.write_text(text, encoding="utf-8")
print("\nF821 fix applied.")
