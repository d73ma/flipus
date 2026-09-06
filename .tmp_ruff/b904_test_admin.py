#!/usr/bin/env python3
"""Test v2 on a single file with detailed logging."""
import ast, re, subprocess, sys
from pathlib import Path

REPO = Path("/Users/jerrymauri/Flipus")
rel = "app/api/v1/admin.py"
full = REPO / rel

# Get B904 lines for this file
proc = subprocess.run(
    [".venv/bin/ruff", "check", rel, "--select", "B904",
     "--output-format", "concise", "--no-fix"],
    cwd=REPO, capture_output=True, text=True
)
line_nos = sorted({
    int(m.group(2))
    for line in (proc.stdout + proc.stderr).splitlines()
    if (m := re.match(r"^(.+?):(\d+):\d+: B904", line))
})
print(f"B904 lines: {line_nos}")

src = full.read_text(encoding="utf-8")
src_lines = src.splitlines(keepends=True)
tree = ast.parse(src)

# Find all raises with their end lines
for ln in line_nos:
    for n in ast.walk(tree):
        if isinstance(n, ast.Raise) and n.lineno == ln:
            print(f"  L{ln} -> end L{n.end_lineno}: {src_lines[ln-1].rstrip()[:80]!r}")
            break

# Now apply v2 fix and check the file parses
print("\n--- applying fix ---")
for ln in reversed(line_nos):
    for n in ast.walk(tree):
        if isinstance(n, ast.Raise) and n.lineno == ln:
            raise_node = n
            break
    # find handler
    class V(ast.NodeVisitor):
        def __init__(self):
            self.found = None
        def visit_ExceptHandler(self, node):
            if node.lineno <= ln <= (node.end_lineno or node.lineno):
                self.found = node
                return
            self.generic_visit(node)
    v = V(); v.visit(tree)
    handler = v.found
    from_clause = f"from {handler.name}" if handler and handler.name else "from None"
    exc_src = ast.unparse(raise_node.exc)
    new_line = f"raise {exc_src} {from_clause}\n"
    end_ln = raise_node.end_lineno or raise_node.lineno
    print(f"  REPLACE L{ln}-{end_ln}: {src_lines[ln-1].rstrip()[:70]!r} -> {new_line.rstrip()[:80]!r}")
    src_lines[ln - 1:end_ln] = [new_line]

# Now try to parse the modified source
new_src = "".join(src_lines)
try:
    ast.parse(new_src)
    print("\n[OK] modified file parses")
except SyntaxError as e:
    print(f"\n[FAIL] SyntaxError at L{e.lineno}: {e.msg}")
    print(f"  text: {e.text!r}")
    # show 3 lines around
    lines = new_src.splitlines()
    if e.lineno and e.lineno <= len(lines):
        for i in range(max(0, e.lineno-3), min(len(lines), e.lineno+2)):
            print(f"    {i+1}: {lines[i]!r}")
