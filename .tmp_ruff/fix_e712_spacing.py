#!/usr/bin/env python3
"""V8 fixer: clean up the spacing on E712 reverts + fix misplaced parens.

Reverts these patterns to `== False)  # noqa: E712` / `== True)  # noqa: E712`:
  - `Column.is_purged== False)  # noqa: E712`  (no space before ==)
  - `Column.is_purged== False)  # noqa: E712,`  (misplaced closing paren)
  - `Column.is_active== True)  # noqa: E712).first()`  (misplaced closing paren)
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
]


def fix_text(text: str) -> tuple[str, int]:
    changes = 0

    # Pattern 1: `Column.is_X== False)  # noqa: E712` -> `Column.is_X == False)  # noqa: E712`
    # Pattern 2: `Column.is_X== True)  # noqa: E712`
    # Pattern 3: `Column.is_X== False)  # noqa: E712,` -> `Column.is_X == False,  # noqa: E712)`
    # Pattern 4: `Column.is_X== True)  # noqa: E712).first()` -> `Column.is_X == True,  # noqa: E712).first()`
    # The closing paren in `== False)  # noqa: E712` was inserted by sed incorrectly.
    # We need to move the `)` to its original location.

    # Replace `is_purged== False)  # noqa: E712` with `is_purged == False,  # noqa: E712)`
    # (i.e. consume the spurious `)`, change `== False)  # noqa: E712,` to `== False,  # noqa: E712)`)

    # Step A: `Column.is_X== False)  # noqa: E712,` -> `Column.is_X == False,  # noqa: E712)`
    pat_a = re.compile(r"(\w+)\.(\w+)== (True|False)\)  # noqa: E712,")
    text, n_a = pat_a.subn(r"\1.\2 == \3,  # noqa: E712)", text)
    changes += n_a

    # Step B: `Column.is_X== False)  # noqa: E712).first()` -> `Column.is_X == False,  # noqa: E712).first()`
    pat_b = re.compile(r"(\w+)\.(\w+)== (True|False)\)  # noqa: E712\)\.first\(\)")
    text, n_b = pat_b.subn(r"\1.\2 == \3,  # noqa: E712).first()", text)
    changes += n_b

    # Step C: `Column.is_X== False)  # noqa: E712` (alone) -> `Column.is_X == False)  # noqa: E712`
    pat_c = re.compile(r"(\w+)\.(\w+)== (True|False)\)  # noqa: E712")
    text, n_c = pat_c.subn(r"\1.\2 == \3)  # noqa: E712", text)
    changes += n_c

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
