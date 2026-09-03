#!/usr/bin/env python3
"""
FASE4-S6A: Audit script — scan semua endpoint modules untuk identifikasi
inline tenant logic yang harus dimigrasi ke TenantScope.

Output: report per-file dengan:
- Endpoint yang sudah pakai require_tenant_scope (aman)
- Endpoint yang punya inline tenant logic (perlu patch)
- Endpoint yang tidak pakai tenant sama sekali (perlu review)
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

API_DIR = Path("app/api/v1")

# Pattern yang dianggap "inline tenant logic"
INLINE_TENANT_KEYWORDS = [
    "tenant_id == current_user",
    "tenant_id = current_user",
    "Tenant.tenant_id",
    "tenant_id in",
    "nama_uni ==",
    "nama_uni = caller",
    "nama_uni == caller",
    "_tenant_ids_for_caller",
    "_get_visible_tenant_ids",
    "_filter_visible_tenants",
    "visible_tenant_ids",
    "caller.tenant_id",
    "user.tenant_id",
]

# Pattern yang dianggap sudah aman (pakai TenantScope)
SAFE_PATTERNS = [
    "require_tenant_scope",
    "TenantScope",
    "tenant_filter",
    "assert_can_access",
    "resolve_tenant_scope",
]


def analyze_endpoint(node: ast.FunctionDef | ast.AsyncFunctionDef, decorators: List[ast.expr]) -> Tuple[str, List[str], List[str]]:
    """Return (method_path, inline_findings, safe_findings)."""
    method_path = node.name
    # Extract HTTP method dari decorators (FastAPI: @router.get("/path"))
    for dec in decorators:
        if isinstance(dec, ast.Call):
            func = dec.func
            if isinstance(func, ast.Attribute) and func.attr in (
                "get", "post", "put", "patch", "delete"
            ):
                # Get path arg
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    method_path = f"{func.attr.upper()} {dec.args[0].value}"

    src = ast.unparse(node)
    inline_findings = []
    safe_findings = []

    for kw in INLINE_TENANT_KEYWORDS:
        if kw in src:
            inline_findings.append(kw)
    for kw in SAFE_PATTERNS:
        if kw in src:
            safe_findings.append(kw)

    # FASE4-S6G: kalau endpoint sudah pakai TenantScope (safe patterns),
    # `visible_tenant_ids` dll adalah legitimate read via scope — BUKAN inline.
    has_safe = len(safe_findings) > 0
    if has_safe:
        inline_findings = []

    return method_path, inline_findings, safe_findings


def analyze_file(path: Path) -> Dict:
    """Analyze satu file dan return summary."""
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return {"file": path.name, "error": f"SyntaxError: {e}", "endpoints": []}

    endpoints = []
    file_uses_tenant_scope = any(p in src for p in SAFE_PATTERNS)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Hanya function yang punya router decorator
            has_router_dec = False
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    if dec.func.attr in ("get", "post", "put", "patch", "delete", "websocket"):
                        has_router_dec = True
                        break

            if not has_router_dec:
                continue

            method, inline, safe = analyze_endpoint(node, node.decorator_list)
            endpoints.append({
                "method": method,
                "inline": inline,
                "safe": safe,
                "line": node.lineno,
            })

    return {
        "file": path.name,
        "uses_tenant_scope": file_uses_tenant_scope,
        "endpoints": endpoints,
    }


def main() -> int:
    files = sorted(API_DIR.glob("*.py"))
    print(f"Scanning {len(files)} endpoint modules in {API_DIR}/\n")
    print("=" * 90)

    summary_rows = []
    detailed = []

    for f in files:
        if f.name == "__init__.py":
            continue
        result = analyze_file(f)
        if "error" in result:
            print(f"❌ {result['file']}: {result['error']}")
            continue

        n_total = len(result["endpoints"])
        n_inline = sum(1 for e in result["endpoints"] if e["inline"])
        n_safe = sum(1 for e in result["endpoints"] if e["safe"])
        n_noop = n_total - n_inline - n_safe

        summary_rows.append({
            "file": result["file"],
            "total": n_total,
            "inline": n_inline,
            "safe": n_safe,
            "noop": n_noop,
            "uses_ts": result["uses_tenant_scope"],
        })

        detailed.append(result)

    # Print summary table
    print(f"{'File':<25} {'Endpoints':>9} {'Inline':>7} {'Safe':>5} {'NoOp':>5} {'usesTS':>7}")
    print("-" * 90)
    for r in summary_rows:
        marker = "✅" if r["inline"] == 0 else "⚠️ "
        print(f"{marker} {r['file']:<23} {r['total']:>9} {r['inline']:>7} {r['safe']:>5} {r['noop']:>5} {'YES' if r['uses_ts'] else 'no':>7}")
    print("-" * 90)

    total_inline = sum(r["inline"] for r in summary_rows)
    total_endpoints = sum(r["total"] for r in summary_rows)
    total_safe = sum(r["safe"] for r in summary_rows)
    print(f"{'TOTAL':<25} {total_endpoints:>9} {total_inline:>7} {total_safe:>5}")
    print()

    # Detail per file: endpoints dengan inline logic
    if total_inline > 0:
        print("=" * 90)
        print("DETAIL: Endpoints dengan inline tenant logic (perlu patch)")
        print("=" * 90)
        for result in detailed:
            file_inline = [e for e in result["endpoints"] if e["inline"]]
            if not file_inline:
                continue
            print(f"\n[{result['file']}]")
            for e in file_inline:
                print(f"  L{e['line']:>4} {e['method']}")
                print(f"        inline patterns: {', '.join(e['inline'])}")
                print(f"        safe patterns:   {', '.join(e['safe']) if e['safe'] else 'NONE — belum pakai TenantScope'}")

    return 0 if total_inline == 0 else 1


if __name__ == "__main__":
    sys.exit(main())