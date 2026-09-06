#!/usr/bin/env python3
"""Fix tiny surgical ruff issues across the codebase."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/Users/jerrymauri/Flipus")


def patch(path: str, edits: list[tuple[int, str, str]]) -> None:
    """Apply a list of (line_no, search_text, replace_text) edits.

    The search_text is matched as a single line; replace_text replaces that line.
    """
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    # Apply in reverse line order so line numbers stay valid
    edits_sorted = sorted(edits, key=lambda e: -e[0])
    for line_no, search, repl in edits_sorted:
        idx = line_no - 1
        old = lines[idx]
        if search not in old:
            print(f"!! MISS in {path}:{line_no}  pattern not found")
            print(f"   expected substring: {search!r}")
            print(f"   actual line:         {old!r}")
            raise SystemExit(1)
        # Preserve trailing newline
        nl = "\n" if old.endswith("\n") else ""
        new_line = old.replace(search, repl)
        lines[idx] = new_line
        print(f"   patched {path}:{line_no}")
    p.write_text("".join(lines), encoding="utf-8")


# ----- B007 unused loop vars -----
# wa_input.py:270 - rename i to _i
patch(
    "app/api/v1/wa_input.py",
    [
        (270, "for i, t in enumerate(tenants[:3], 1):", "for _i, t in enumerate(tenants[:3], 1):"),
    ],
)

# scripts/smoke_m8.py:341 - rename msg to _msg
patch(
    "scripts/smoke_m8.py",
    [
        (341, "for name, ok, msg in results:", "for name, ok, _msg in results:"),
    ],
)

# ----- UP038 isinstance tuple -> X | Y -----
# scripts/audit_tenant_scope.py:92 - isinstance with (ast.FunctionDef, ast.AsyncFunctionDef)
patch(
    "scripts/audit_tenant_scope.py",
    [
        (92, "isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))",
             "isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)"),
    ],
)

# ----- E711 SQLAlchemy filter -----
# register.py:394 - Tenant.misi_konferens_id == None -> .is_(None)
patch(
    "app/api/v1/register.py",
    [
        (394, "Tenant.misi_konferens_id == None,", "Tenant.misi_konferens_id.is_(None),"),
    ],
)

print("\nAll tiny surgical fixes applied.")