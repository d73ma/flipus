#!/usr/bin/env python3
"""V5 T201 fixer — line-targeted regex + AST-based module logger insertion.

- `print(...)` → `logger.exception(...)` or `log.error(...)` using safe regex with lookahead.
- Module-level `import logging` + `logger = logging.getLogger(__name__)` inserted AFTER last top-level import (via AST).
"""
from __future__ import annotations

import ast
import re
import subprocess as sp
from pathlib import Path

REPO = Path("/Users/jerrymauri/Flipus")

FILES = [
    ("app/api/v1/laporan_gabungan.py", "logger", True, True),
    ("app/api/v1/m8_managed.py", "logger", True, True),
    ("app/api/v1/pengeluaran_ocr.py", "logger", False, False),
    ("app/api/v1/reports.py", "logger", True, True),
    ("app/api/v1/scanner.py", "logger", True, True),
    ("app/api/v1/wa_input.py", "log", False, False),
]

# Drop `, file=XXX` and `, flush=True` keyword args in print().
# CRITICAL: trailing comma is OPTIONAL, and only consumed if NOT followed by another kwarg.
PAT_FILE_KWARG = re.compile(
    r""",\s*file\s*=\s*(?:[A-Za-z_]\w*\s*\.\s*[A-Za-z_]\w*|[A-Za-z_]\w*)(?:\s*,(?!\s*\w+\s*=))?""",
    re.MULTILINE,
)
PAT_FLUSH_KWARG = re.compile(
    r""",\s*flush\s*=\s*(?:True|False)(?:\s*,(?!\s*\w+\s*=))?""",
    re.MULTILINE,
)


def strip_print_kwargs(s: str) -> str:
    s = PAT_FILE_KWARG.sub("", s)
    s = PAT_FLUSH_KWARG.sub("", s)
    return s


def find_print_span(lines: list[str], lineno_0idx: int, start_col: int) -> tuple[int, int] | None:
    depth = 0
    for i in range(lineno_0idx, len(lines)):
        line = lines[i]
        j = start_col if i == lineno_0idx else 0
        while j < len(line):
            ch = line[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return (lineno_0idx, i)
            j += 1
    return None


def fix_print_line(lines: list[str], lineno_1idx: int, logger_name: str, in_except: bool) -> int:
    lineno_0 = lineno_1idx - 1
    line = lines[lineno_0]
    m = re.search(r"\bprint\s*\(", line)
    if not m:
        return 0
    span = find_print_span(lines, lineno_0, m.end() - 1)
    if not span:
        return 0
    start_line, end_line = span
    method = "exception" if in_except else "error"
    new_prefix = f"{logger_name}.{method}("

    if start_line == end_line:
        inner_start = m.end()
        depth = 1
        j = inner_start
        while j < len(line):
            if line[j] == "(":
                depth += 1
            elif line[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= len(line):
            return 0
        body = line[inner_start:j]
        body = strip_print_kwargs(body)
        leading = line[: line.index("print(")]
        new_line = leading + new_prefix + body + ")" + line[j + 1 :]
        lines[start_line] = new_line
        return 1
    else:
        first_line = lines[start_line]
        inner_start = first_line.index("print(") + len("print(")
        body_parts = [first_line[inner_start:]]
        for k in range(start_line + 1, end_line):
            body_parts.append(lines[k])
        last_line = lines[end_line]
        depth = 1
        j = 0
        while j < len(last_line):
            if last_line[j] == "(":
                depth += 1
            elif last_line[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= len(last_line):
            return 0
        body_parts.append(last_line[:j])
        body = " ".join(p.strip() for p in body_parts)
        body = strip_print_kwargs(body)
        leading = first_line[: first_line.index("print(")]
        new_line = leading + new_prefix + body + ")\n"
        new_lines = lines[:start_line] + [new_line] + lines[end_line + 1 :]
        lines.clear()
        lines.extend(new_lines)
        return 1


def ensure_module_logger(path: Path, logger_name: str, needs_import: bool, needs_decl: bool) -> bool:
    """Insert module-level `import logging` and/or `logger = logging.getLogger(__name__)` if missing.
    Uses AST to find the correct insertion point (after last top-level import or docstring)."""
    text = path.read_text()
    has_import = "import logging" in text
    has_decl = f"{logger_name} = logging.getLogger" in text
    if (not needs_import or has_import) and (not needs_decl or has_decl):
        return False

    tree = ast.parse(text)
    # Find the last top-level Import/ImportFrom; otherwise insert after module docstring.
    last_end_lineno = 0  # 1-based end line of last top-level statement we anchor on
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last_end_lineno = node.end_lineno
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            # Module docstring
            if last_end_lineno == 0:
                last_end_lineno = node.end_lineno

    lines = text.splitlines(keepends=True)
    # last_end_lineno is 1-based. To insert AFTER line N, use splitlines index N (0-based = N-1, insert at N)
    # For example: line 24 is at index 23 (0-based, ends with \n). We want to insert after it = at index 24.
    insert_idx = last_end_lineno  # 1-based end_lineno is the position to insert at (in 0-based splitlines index)
    if insert_idx > len(lines):
        insert_idx = len(lines)

    insertions = []
    if needs_import and not has_import:
        insertions.append("import logging\n")
    if needs_decl and not has_decl:
        insertions.append(f'{logger_name} = logging.getLogger(__name__)\n')

    prefix = lines[:insert_idx]
    suffix = lines[insert_idx:]
    new_lines = prefix + insertions + ["\n"] + suffix
    new_text = "".join(new_lines)
    path.write_text(new_text)
    return True


def main():
    proc = sp.run(
        [".venv/bin/ruff", "check", "--select", "T201", "--no-fix", "--output-format=concise"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    violations = []
    for line in proc.stdout.splitlines():
        m = re.match(r"^([^:]+):(\d+):\d+:\s+T201", line)
        if m:
            violations.append((m.group(1), int(m.group(2))))

    by_file = {}
    for path, ln in violations:
        by_file.setdefault(path, []).append(ln)

    file_cfg = {path: (name, imp, decl) for path, name, imp, decl in FILES}

    total = 0
    for path, lines_list in by_file.items():
        if path.startswith(".tmp_ruff") or path.startswith(".ruff_e402"):
            continue
        if path not in file_cfg:
            print(f"!! No config for {path}")
            continue
        logger_name, needs_import, needs_decl = file_cfg[path]
        full = REPO / path
        text = full.read_text()
        original_text = text

        in_except_lines = set()
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.Try):
                    for handler in node.handlers:
                        for child in ast.walk(handler):
                            ln = getattr(child, "lineno", None)
                            if ln:
                                end = getattr(child, "end_lineno", ln)
                                for x in range(ln, end + 1):
                                    in_except_lines.add(x)
        except SyntaxError as e:
            print(f"!! Failed to parse {path}: {e}")
            continue

        lines = text.splitlines(keepends=True)
        for ln in sorted(lines_list, reverse=True):
            in_exc = ln in in_except_lines
            n = fix_print_line(lines, ln, logger_name, in_exc)
            total += n

        new_text = "".join(lines)
        if new_text != original_text:
            full.write_text(new_text)
            ensure_module_logger(full, logger_name, needs_import, needs_decl)
            # Verify compile
            try:
                ast.parse(full.read_text())
                print(f"+ {path}: {len(lines_list)} print calls → logger ({logger_name}) ✓ compiles")
            except SyntaxError as e:
                print(f"+ {path}: {len(lines_list)} print calls → logger ({logger_name}) ✗ SYNTAX: {e}")
        else:
            print(f"  {path}: no changes")

    print(f"\n=== Total: {total} print calls converted ===")


if __name__ == "__main__":
    main()