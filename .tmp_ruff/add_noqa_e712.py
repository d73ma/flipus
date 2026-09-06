#!/usr/bin/env python3
"""Append '# noqa: E712' to SQLAlchemy Column == False/True lines missing it.

Targets lines matching:
    .filter(<Model>.<col> == False)      (or True)
    <Model>.<col> == False,              (or True, in multi-arg filter)

Skips lines that already have `# noqa: E712`.
"""
import re
import sys
from pathlib import Path

FILES = [
    "app/api/v1/laporan_gabungan.py",
    "app/api/v1/pengeluaran_ocr.py",
    "app/api/v1/reports.py",
    "app/api/v1/wa_input.py",
]

# Match: <ident>.<ident> == (False|True), with optional trailing comma/paren
PATTERN = re.compile(
    r'(\b[A-Z][A-Za-z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*\s*==\s*(?:False|True))'
    r'((?:\s*,)?)(?!.*#\s*noqa:\s*E712)([ \t]*)$'
)

NOQA = "  # noqa: E712"

total_fixed = 0
for rel in FILES:
    p = Path(rel)
    if not p.exists():
        print(f"SKIP (missing): {rel}", file=sys.stderr)
        continue
    text = p.read_text(encoding="utf-8")
    new_lines = []
    file_fixed = 0
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        # Skip blank lines or already annotated
        if "noqa: E712" in stripped:
            new_lines.append(line)
            continue
        # Match
        m = PATTERN.search(stripped)
        if m:
            # Insert noqa at end of line (preserve trailing newline)
            indent_end = len(stripped)
            # Append noqa before newline
            new_stripped = stripped + NOQA
            new_lines.append(new_stripped + "\n")
            file_fixed += 1
        else:
            new_lines.append(line)
    if file_fixed:
        p.write_text("".join(new_lines), encoding="utf-8")
    print(f"{rel}: +{file_fixed} noqa:E712", file=sys.stderr)
    total_fixed += file_fixed

print(f"TOTAL: {total_fixed}", file=sys.stderr)
