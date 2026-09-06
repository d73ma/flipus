#!/usr/bin/env python3
"""Add `# noqa: E402` to all E402-flagged import lines."""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path("/Users/jerrymauri/Flipus")


def main():
    proc = subprocess.run(
        [".venv/bin/ruff", "check", "app/", "tests/",
         "--select", "E402",
         "--output-format", "concise"],
        cwd=REPO, capture_output=True, text=True
    )
    by_file: dict[str, list[int]] = {}
    for line in (proc.stdout + proc.stderr).splitlines():
        m = re.match(r"^(.+?):(\d+):\d+: E402", line)
        if not m:
            continue
        path, lineno = m.group(1), int(m.group(2))
        by_file.setdefault(path, []).append(lineno)

    total = 0
    for rel, line_nums in by_file.items():
        full = REPO / rel
        text = full.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        n = 0
        for ln in sorted(set(line_nums)):
            idx = ln - 1
            original = lines[idx]
            if "noqa" in original:
                continue
            stripped = original.rstrip("\n").rstrip()
            if not stripped.lstrip().startswith(("import ", "from ")):
                continue
            if not stripped.endswith("# noqa: E402"):
                lines[idx] = stripped + "  # noqa: E402\n"
                n += 1
        full.write_text("".join(lines), encoding="utf-8")
        print(f"{rel}: {n}/{len(set(line_nums))} lines")
        total += n
    print(f"TOTAL: {total}")


if __name__ == "__main__":
    sys.exit(main() or 0)