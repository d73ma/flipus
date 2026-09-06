#!/usr/bin/env python3
"""Add `# noqa: E402` to every import line that ruff flagged E402 on.

Strategy: walk each flagged (file, line) pair, read the line, append `  # noqa: E402`
unless it already has a `# noqa` comment.
"""
from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path("/Users/jerrymauri/Flipus")

# Collect (file, line) pairs from ruff
proc = subprocess.run(
    [".venv/bin/ruff", "check", ".", "--select", "E402", "--output-format=concise"],
    cwd=ROOT,
    capture_output=True,
    text=True,
)
hits: dict[str, list[int]] = defaultdict(list)
# ruff returns exit code 1 when violations found; output is on stdout
for line in proc.stdout.splitlines():
    m = re.match(r"^([^:]+):(\d+):\d+: E402", line)
    if m:
        hits[m.group(1)].append(int(m.group(2)))

total = 0
for rel, line_nos in hits.items():
    p = ROOT / rel
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    # Process in reverse so earlier line numbers stay valid
    for ln in sorted(line_nos, reverse=True):
        idx = ln - 1
        old = lines[idx]
        if "# noqa" in old:
            continue  # already has noqa
        # Strip trailing newline to add comment, then re-add
        stripped = old.rstrip("\n")
        # Only annotate import lines (rough check: starts with `import` or `from`)
        if not re.match(r"^(import |from )", stripped):
            print(f"   !! skip non-import {rel}:{ln}: {old!r}")
            continue
        new = stripped + "  # noqa: E402\n"
        lines[idx] = new
        total += 1
        print(f"   patched {rel}:{ln}")
    p.write_text("".join(lines), encoding="utf-8")

print(f"\nE402: appended `# noqa: E402` to {total} import lines.")
