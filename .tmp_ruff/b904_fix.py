#!/usr/bin/env python3
"""B904 fixer: convert `raise X` inside `except Y as err:` blocks to `raise X from err`.

Strategy:
- Parse file with ast.
- Walk for `except ... as <name>:` clauses.
- For each `raise <expr>` inside the handler, if it has no `__cause__` (no `from` clause)
  and the raised exception is NOT a re-raise of `err` itself (`raise err`),
  rewrite the AST node to add `from err`.

Approach: tokenize the source, find each except-handler span, then in that span
rewrite the *first* `raise <expr>` line that lacks `from`.
"""
import ast
import re
import subprocess
import sys
from pathlib import Path

REPO = Path("/Users/jerrymauri/Flipus")


def parse_ruff_output(output: str) -> dict[str, list[int]]:
    by_file: dict[str, list[int]] = {}
    for line in output.splitlines():
        m = re.match(r"^(.+?):(\d+):\d+: B904", line)
        if not m:
            continue
        path, lineno = m.group(1), int(m.group(2))
        by_file.setdefault(path, []).append(lineno)
    return by_file


def fix_file(file_path: Path, target_lines: list[int]) -> int:
    """For each B904 line, find the enclosing except clause's `as err` binding,
    and rewrite the raise statement to add `from err`."""
    src = file_path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # Build (handler, asname) for every except handler
    handlers_by_line: dict[int, tuple[ast.ExceptHandler, str | None]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            asname = node.name  # str | None
            handlers_by_line[node.lineno] = (node, asname)

    # Map every line inside handler.body to its handler
    line_to_handler: dict[int, tuple[ast.ExceptHandler, str | None]] = {}
    for h, asname in handlers_by_line.values():
        h_start = h.lineno
        h_end = h.end_lineno or h.lineno
        for ln in range(h_start, h_end + 1):
            line_to_handler.setdefault(ln, (h, asname))

    # For each target line, find the closest enclosing handler with an `as name`
    edits: list[tuple[int, str, str]] = []  # (line_no, old_text, new_text)
    src_lines = src.splitlines(keepends=True)

    for ln in sorted(set(target_lines)):
        # Walk up from ln to find a handler where ln ∈ handler.body
        handler = None
        asname = None
        for cand_ln, (h, an) in line_to_handler.items():
            if h.lineno <= ln <= (h.end_lineno or h.lineno):
                handler = h
                asname = an
                # use the *outermost* (first) handler that contains this line — actually we want the *innermost*
        # Re-pick innermost
        candidates = [
            (h, an) for h, an in handlers_by_line.values()
            if h.lineno <= ln <= (h.end_lineno or h.lineno)
        ]
        if not candidates:
            print(f"  !! {file_path.name}:{ln}: no enclosing except", file=sys.stderr)
            continue
        handler, asname = min(candidates, key=lambda kv: kv[0].end_lineno - kv[0].lineno)
        if not asname:
            print(f"  !! {file_path.name}:{ln}: handler has no `as` binding", file=sys.stderr)
            continue

        # Inspect the raise statement at ln
        # Find the raise node whose lineno == ln
        target_raise = None
        for node in ast.walk(handler):
            if isinstance(node, ast.Raise) and node.lineno == ln:
                target_raise = node
                break
        if target_raise is None:
            print(f"  !! {file_path.name}:{ln}: no raise node at this line", file=sys.stderr)
            continue
        if target_raise.cause is not None:
            # Already has `from`, skip
            continue

        # The raise expr: `raise Foo("msg")` etc.
        old = src_lines[ln - 1]
        # If it's a bare re-raise `raise`, skip (not what B904 flags)
        if target_raise.exc is None:
            continue
        exc_text = ast.unparse(target_raise.exc).strip()
        # Check if exc is just `asname` (re-raise) → no change
        if exc_text == asname:
            continue

        # Rewrite: append `  # noqa: B904` is wrong — instead add ` from err`
        # Ensure trailing newline preserved
        stripped = old.rstrip("\n")
        if not stripped.endswith("from " + asname):
            new = stripped + f" from {asname}\n"
            src_lines[ln - 1] = new
            edits.append((ln, stripped, new.rstrip("\n")))

    if edits:
        file_path.write_text("".join(src_lines), encoding="utf-8")
    return len(edits)


def main():
    proc = subprocess.run(
        [".venv/bin/ruff", "check", "app/", "tests/",
         "--select", "B904",
         "--output-format", "concise",
         "--no-fix"],
        cwd=REPO, capture_output=True, text=True
    )
    by_file = parse_ruff_output(proc.stdout + proc.stderr)
    total = 0
    for rel, line_nums in by_file.items():
        full = REPO / rel
        n = fix_file(full, line_nums)
        print(f"{rel}: fixed {n}/{len(set(line_nums))}")
        total += n
    print(f"TOTAL: {total}")


if __name__ == "__main__":
    sys.exit(main() or 0)