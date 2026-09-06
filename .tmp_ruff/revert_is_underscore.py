#!/usr/bin/env python3
"""
V7 — REVERT all `.is_(False)` / `.is_(True)` → `== False` / `== True`
for SQLAlchemy Column comparisons, AND add `# noqa: E712` to suppress ruff.

Why: SQLAlchemy 1.x/2.x renders `Column.is_(False)` as `IS 0` in SQLite,
which is INVALID SQL. The original `== False` compiles to `= 0` which works.

This restores the pre-V5 baseline behavior while keeping ruff clean.
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def revert_file(rel_path: str) -> tuple[int, int]:
    """Replace `.is_(False)` → `== False  # noqa: E712` and similar."""
    path = ROOT / rel_path
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return 0, 0  # binary file, skip
    new_text = text

    # Match `.is_(False)` or `.is_(True)` (with optional whitespace)
    # We want to replace with `== False` / `== True` + noqa comment if needed.
    n_false = len(re.findall(r"\.is_\(\s*False\s*\)", new_text))
    n_true = len(re.findall(r"\.is_\(\s*True\s*\)", new_text))

    # Replace `.is_(False)` → `== False  # noqa: E712`
    new_text = re.sub(
        r"\.is_\(\s*False\s*\)",
        "== False  # noqa: E712",
        new_text,
    )
    new_text = re.sub(
        r"\.is_\(\s*True\s*\)",
        "== True  # noqa: E712",
        new_text,
    )

    if new_text != text:
        path.write_text(new_text)
    return n_false, n_true


def find_files_with_is_underscore():
    result = subprocess.run(
        ["grep", "-rln", r"\.is_(True\|False)", "app/"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    # grep returns paths relative to cwd (e.g. "app/api/v1/sync.py")
    return [Path(p) for p in result.stdout.strip().split("\n") if p]


def main() -> int:
    files = find_files_with_is_underscore()
    total_false = total_true = 0
    for f in files:
        rel = f.as_posix()
        nf, nt = revert_file(rel)
        total_false += nf
        total_true += nt
        print(f"{rel}: {nf} is_(False), {nt} is_(True) → == False/True")
    print(f"\nTotal: {total_false} is_(False) + {total_true} is_(True) reverted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())