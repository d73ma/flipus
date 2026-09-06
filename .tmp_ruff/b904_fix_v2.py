#!/usr/bin/env python3
"""B904 fixer v2 — uses ast.unparse to safely rewrite multi-line raises.

Strategy:
  1. Parse each file with ast.parse()
  2. Find every `raise <expr>` (no `__cause__`) inside an `except X as Y:` handler
  3. Use ast.unparse(raise.exc) to get a valid single-line exception expression
  4. Replace src_lines[raise.lineno-1 : raise.end_lineno] with the new single-line raise
  5. For handlers without `as name` → use `from None`
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

REPO = Path("/Users/jerrymauri/Flipus")


def ruff_b904_lines() -> dict[str, set[int]]:
    """Run ruff, return {rel_path: {lineno, ...}} for B904 errors."""
    proc = subprocess.run(
        [".venv/bin/ruff", "check", "app/", "tests/",
         "--select", "B904", "--output-format", "concise", "--no-fix"],
        cwd=REPO, capture_output=True, text=True
    )
    out: dict[str, set[int]] = {}
    for line in (proc.stdout + proc.stderr).splitlines():
        m = re.match(r"^(.+?):(\d+):\d+: B904", line)
        if not m:
            continue
        path, lineno = m.group(1), int(m.group(2))
        out.setdefault(path, set()).add(lineno)
    return out


def find_enclosing_handler(tree: ast.AST, target_lineno: int) -> ast.ExceptHandler | None:
    """Walk tree to find the ExceptHandler that contains target_lineno."""
    class V(ast.NodeVisitor):
        def __init__(self):
            self.found: ast.ExceptHandler | None = None
        def visit_ExceptHandler(self, node: ast.ExceptHandler):
            start = node.lineno
            end = getattr(node, "end_lineno", None) or start
            if start <= target_lineno <= end:
                self.found = node
                return  # no need to descend
            self.generic_visit(node)
    v = V()
    v.visit(tree)
    return v.found


def find_raise_at_lineno(tree: ast.AST, target_lineno: int) -> ast.Raise | None:
    """Find the Raise node whose lineno == target_lineno (and no existing cause)."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise):
            continue
        if node.lineno != target_lineno:
            continue
        if node.exc is None:
            continue  # bare `raise` re-raise
        if node.cause is not None:
            continue  # already has `from`
        return node
    return None


def fix_file(rel: str, line_nos: set[int]) -> tuple[int, int, list[str]]:
    """Returns (fixed, skipped, problems)."""
    full = REPO / rel
    src = full.read_text(encoding="utf-8")
    src_lines = src.splitlines(keepends=True)
    tree = ast.parse(src)

    fixed = 0
    problems: list[str] = []

    # Build map: lineno → (Raise, ExceptHandler)
    targets: list[tuple[int, int, ast.Raise, ast.ExceptHandler | None]] = []
    for ln in line_nos:
        handler = find_enclosing_handler(tree, ln)
        raise_node = find_raise_at_lineno(tree, ln)
        if raise_node is None:
            problems.append(f"{rel}:{ln}: raise node not found")
            continue
        targets.append((ln, raise_node.end_lineno or raise_node.lineno, raise_node, handler))

    # Process in REVERSE line order so earlier line numbers stay valid
    for ln, end_ln, raise_node, handler in sorted(targets, key=lambda t: -t[0]):
        # Determine `from` clause
        if handler is not None and handler.name is not None:
            from_clause = f"from {handler.name}"
        else:
            from_clause = "from None"

        # Reconstruct exception expression on one line
        try:
            exc_src = ast.unparse(raise_node.exc)  # type: ignore[arg-type]
        except Exception as e:
            problems.append(f"{rel}:{ln}: ast.unparse failed: {e}")
            continue

        # Build new line
        # Preserve leading whitespace from the original first line
        first_line = src_lines[ln - 1]
        leading_ws = first_line[: len(first_line) - len(first_line.lstrip(" \t"))]
        new_line = f"{leading_ws}raise {exc_src} {from_clause}\n"
        new_lines = src_lines[:]
        # Replace [start_idx, end_idx) with single line
        new_lines[ln - 1:end_ln] = [new_line]
        src_lines = new_lines
        fixed += 1

    if fixed:
        full.write_text("".join(src_lines), encoding="utf-8")
    return fixed, 0, problems


def main():
    by_file = ruff_b904_lines()
    total = 0
    all_problems: list[str] = []
    for rel, lines in sorted(by_file.items()):
        fixed, skipped, problems = fix_file(rel, lines)
        print(f"{rel}: B904 lines={len(lines)} fixed={fixed} problems={len(problems)}")
        for p in problems:
            print(f"  ! {p}")
        total += fixed
        all_problems.extend(problems)
    print(f"\nTOTAL fixed: {total}")
    if all_problems:
        print(f"Problems: {len(all_problems)}")
    # Verify
    print("\n--- post-fix ruff B904 ---")
    subprocess.run(
        [".venv/bin/ruff", "check", "app/", "tests/",
         "--select", "B904", "--output-format", "concise", "--no-fix"],
        cwd=REPO
    )


if __name__ == "__main__":
    main()
