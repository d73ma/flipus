"""
Surgical fixer for ruff E402 errors where imports are intentionally placed
AFTER module-level side effects (logging init, env load, _setup_logging call, etc).

Strategy: append `# noqa: E402` to each flagged import line.
"""

import re
import sys
from pathlib import Path

REPO = Path("/Users/jerrymauri/Flipus")


def parse_ruff_output(output: str) -> dict[str, list[int]]:
    """Parse `ruff check --output-format=concise` output.

    Format: `path/to/file.py:LINE:COL: E402 ...`
    """
    by_file: dict[str, list[int]] = {}
    for line in output.splitlines():
        m = re.match(r"^(.+?):(\d+):\d+: (E\d+)", line)
        if not m:
            continue
        path, lineno, code = m.group(1), int(m.group(2)), m.group(3)
        by_file.setdefault(path, []).append(lineno)
    return by_file


def apply_noqa(file_path: Path, line_numbers: list[int]) -> int:
    """Add `# noqa: E402` to each target line. Skip lines that already have noqa."""
    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    fixed = 0
    for ln in sorted(set(line_numbers)):
        idx = ln - 1
        if idx >= len(lines):
            continue
        original = lines[idx]
        if "noqa" in original:
            continue  # already has noqa comment
        # Strip trailing newline/whitespace, add comment, re-add newline
        stripped = original.rstrip("\n")
        if not stripped.lstrip().startswith(("import ", "from ")):
            # Not actually an import — skip silently
            continue
        lines[idx] = stripped + "  # noqa: E402\n"
        fixed += 1
    file_path.write_text("".join(lines), encoding="utf-8")
    return fixed


def main():
    if len(sys.argv) > 1:
        output = sys.stdin.read() if sys.argv[1] == "-" else Path(sys.argv[1]).read_text()
    else:
        output = sys.stdin.read()
    by_file = parse_ruff_output(output)
    total = 0
    for rel_path, lines in by_file.items():
        full = REPO / rel_path
        if not full.exists():
            print(f"!! file missing: {full}", file=sys.stderr)
            continue
        n = apply_noqa(full, lines)
        print(f"{rel_path}: noqa added to {n}/{len(lines)} lines")
        total += n
    print(f"TOTAL noqa added: {total}")


if __name__ == "__main__":
    main()
