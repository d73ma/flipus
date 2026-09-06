#!/usr/bin/env python3
"""V9 fixer: handle ALL variants of misplaced closing-paren in noqa comments.

The V7 reverter pattern was: `,  # noqa: E712` followed by `)` or `).first()`.
For lines where `.is_(True)`/`.is_(False)` was the LAST argument inside a `()`,
the closing `)` got trapped in the comment, e.g.:

  WRONG: `Tenant.is_active == True,  # noqa: E712).first()`
         (the `)` closes the filter(), then `).first()` is in the comment — syntax broken)

  CORRECT forms (based on original code structure):
    A. `== False)  # noqa: E712` — column is the last arg of an outer call
       e.g. `.filter(Col == False)  # noqa: E712`
    B. `== True)  # noqa: E712.  .first()` — column closes filter(), then `.first()` after comment
       e.g. `.filter(Col == True)  # noqa: E712.  .first()`

This script:
  1. Fixes Pattern A: `== False/True)  # noqa: E712,` -> `== False/True,  # noqa: E712)`
  2. Fixes Pattern B: `== False/True)  # noqa: E712).first()` -> `== False/True)  # noqa: E712.  .first()`
  3. Adds space before == if missing: `Col== False` -> `Col == False`
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # .tmp_ruff/ -> Flipus

FILES = [
    "app/api/v1/kuitansi.py",
    "app/api/v1/dashboard.py",
    "app/api/v1/quick_input.py",
    "app/api/v1/agregat.py",
    "app/api/v1/sync.py",
    "app/api/v1/pengeluaran.py",
    "app/api/v1/pengeluaran_wa.py",
]


def fix_text(text: str) -> tuple[str, int]:
    changes = 0

    # Pattern B: `== False/True)  # noqa: E712).first()` -> `== False/True)  # noqa: E712.  .first()`
    pat_b = re.compile(r"== (True|False)\)  # noqa: E712\)\.first\(\)")
    text, n_b = pat_b.subn(r"== \1)  # noqa: E712.  .first()", text)
    changes += n_b

    # Pattern A: `== False/True)  # noqa: E712,` -> `== False/True,  # noqa: E712)`
    pat_a = re.compile(r"== (True|False)\)  # noqa: E712,")
    text, n_a = pat_a.subn(r"== \1,  # noqa: E712)", text)
    changes += n_a

    # Pattern C: `== False/True)  # noqa: E712)` (followed by outer `).first()`) -> handled by A and B above

    # Add missing space before ==: `Col== False` -> `Col == False`
    pat_sp = re.compile(r"(\w)== (True|False)")
    text, n_sp = pat_sp.subn(r"\1 == \2", text)
    changes += n_sp

    return text, changes


def main() -> int:
    total = 0
    for rel in FILES:
        path = ROOT / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            print(f"SKIP {rel}: {e}", file=sys.stderr)
            continue
        new_text, n = fix_text(text)
        if n > 0 and new_text != text:
            path.write_text(new_text, encoding="utf-8")
            print(f"OK {rel}: {n} change(s)")
            total += n
        else:
            print(f"-- {rel}: no changes")
    print(f"\nTotal changes: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
