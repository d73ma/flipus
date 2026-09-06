#!/usr/bin/env python3
"""
V6 T201 fixer follow-up — HOIST module-level logger.

Problem: V5 fixer skipped files that already had `import logging` SOMEWHERE,
even if it was inside a function. So reports.py and scanner.py ended up with
`logger.exception(...)` calls in functions where `logger` is not defined.

Fix: For each target file:
1. Find any top-level `import logging` (if exists, skip — already good)
2. Otherwise, hoist the FIRST function-local `import logging` + `logger = ...`
   block to module level (after last top-level import) and remove the local copy.
3. Verify with a ruff check + python -c 'import' compile.

Tested on: app/api/v1/reports.py, app/api/v1/scanner.py
"""
import ast
import re
import sys
import subprocess
from pathlib import Path

# Script lives at /Users/jerrymauri/Flipus/.tmp_ruff/fix_t201_v6_hoist.py
# parents[0]=.tmp_ruff, parents[1]=Flipus (project root).
ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "app" / "api" / "v1" / "reports.py",
    ROOT / "app" / "api" / "v1" / "scanner.py",
]

# Pattern for the local block to detect:
#     import logging
#     import traceback      (optional, may have other imports)
#     logger = logging.getLogger(__name__)
LOCAL_LOGGER_BLOCK = re.compile(
    r"""
    ^[ \t]+ (?P<imports>(?:(?:import|from)\s+[^\n]+\n)+)        # indented import lines
    [ \t]+ logger\s*=\s*logging\.getLogger\(\s*__name__\s*\)\s*\n
    """,
    re.MULTILINE | re.VERBOSE,
)

# Simpler fallback (no extra imports — just `import logging` then logger):
SIMPLE_LOGGER_BLOCK = re.compile(
    r"""
    ^[ \t]+ import\s+logging\s*\n
    [ \t]+ logger\s*=\s*logging\.getLogger\(\s*__name__\s*\)\s*\n
    """,
    re.MULTILINE | re.VERBOSE,
)


def find_module_level_import_insertion(text: str) -> int:
    """Return the 0-indexed LINE NUMBER (exclusive end) where module-level
    `import logging` + `logger = ...` should be inserted.
    Uses AST to find the last top-level Import/ImportFrom statement."""
    tree = ast.parse(text)
    last_end_lineno_1idx = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            # node.end_lineno is 1-indexed, exclusive end of last import line
            last_end_lineno_1idx = max(last_end_lineno_1idx, node.end_lineno or 0)
    # We want to insert AFTER this last import line.
    # Convert to 0-indexed line number exclusive end for slicing.
    return last_end_lineno_1idx  # 1-indexed last import line; insert at this 0-index


def find_local_logger_block(text: str) -> tuple[int, int] | None:
    """Find a local `import logging` + `logger = logging.getLogger(__name__)`
    block inside a function. Returns (start_0idx, end_0idx_exclusive) or None."""
    lines = text.splitlines(keepends=True)
    n = len(lines)
    for i, line in enumerate(lines):
        # Look for indented `import logging`
        m = re.match(r"^(\s+)import\s+logging\s*$", line)
        if not m:
            continue
        indent = m.group(1)
        # Check next 1-3 lines for `logger = logging.getLogger(__name__)`
        # at the same indent.
        for j in range(i + 1, min(i + 6, n)):
            jline = lines[j]
            if jline.startswith(indent + "logger = logging.getLogger(__name__)"):
                # Make sure line after is blank or dedented (end of local block)
                k = j + 1
                # Consume blank lines at same indent? Actually blank lines have
                # no indent prefix; we just consume one trailing blank if any.
                end_excl = j + 1
                if k < len(lines) and lines[k].strip() == "":
                    end_excl = k + 1
                return i, end_excl
    return None


def has_module_level_import_logging(tree: ast.AST) -> bool:
    """Return True if there's a top-level `import logging` already."""
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "logging":
                    return True
        if isinstance(node, ast.ImportFrom):
            if node.module == "logging":
                return True
    return False


def hoist_module_logger(path: Path) -> str:
    text = path.read_text()
    tree = ast.parse(text)

    if has_module_level_import_logging(tree):
        return f"SKIP: {path.name} — already has module-level `import logging`"

    # Find local block
    block = find_local_logger_block(text)
    if block is None:
        return f"WARN: {path.name} — no local `import logging` + `logger = ...` block found"

    start, end_excl = block
    lines = text.splitlines(keepends=True)
    local_block_lines = lines[start:end_excl]
    local_block_text = "".join(local_block_lines)

    # The local block looks like:
    #     import logging\n
    #     logger = logging.getLogger(__name__)\n
    # (possibly with extra imports between — but we'll keep them with logger)
    # Strip leading indent and prepare module-level form.
    dedented = []
    for ln in local_block_lines:
        if ln.strip() == "":
            dedented.append("\n")
        else:
            dedented.append(ln.lstrip())
    module_block = "".join(dedented).rstrip("\n") + "\n"

    # Find module-level insertion point (after last top-level import)
    insert_after_lineno_1idx = find_module_level_import_insertion(text)
    # Convert to 0-indexed line number for splitlines/keepends slicing
    insert_at_0idx = insert_after_lineno_1idx  # 0-indexed line index to INSERT AT

    # Build new text: lines[0..insert_at] + module_block + lines[insert_at..start] + lines[end_excl..]
    new_lines = (
        lines[:insert_at_0idx]
        + [module_block]
        + lines[insert_at_0idx:start]
        + lines[end_excl:]
    )
    new_text = "".join(new_lines)
    path.write_text(new_text)
    return (
        f"OK: {path.name} — hoisted module-level logger, removed local block "
        f"(was lines {start+1}..{end_excl} in original)"
    )


def verify(path: Path) -> str:
    # ruff check (no-fix) T201
    ruff = ROOT / ".venv" / "bin" / "ruff"
    if ruff.exists():
        r = subprocess.run(
            [str(ruff), "check", str(path), "--no-fix"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        ruff_out = (r.stdout + r.stderr).strip().splitlines()[-3:]
        ruff_out = "\n".join(ruff_out) if ruff_out else "(no output)"
    else:
        ruff_out = "(ruff not found)"
    # python compile
    py = subprocess.run(
        ["python3", "-c", f"import ast; ast.parse(open({str(path)!r}).read()); print('OK')"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    pyc = (py.stdout + py.stderr).strip()
    return f"  ruff: {ruff_out}\n  py  : {pyc}"


def main() -> int:
    for path in TARGETS:
        msg = hoist_module_logger(path)
        print(msg)
        print(verify(path))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())