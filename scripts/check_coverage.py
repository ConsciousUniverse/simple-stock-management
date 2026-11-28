"""
Coverage gate for the transfer business logic.

Reads coverage.json (coverage.py with --branch) and fails unless every statement and every
branch inside the rule functions is covered.  Overall file coverage is deliberately not used:
views.py also holds item-management viewsets that are outside the two tested workflows.

Usage: python scripts/check_coverage.py [required_percent]   (default 100)
"""
import ast
import json
import pathlib
import sys

FILE = "stock_manager/views.py"
FUNCS = {"transfer_item", "transfer_to_shop", "submit_transfer_request", "complete_transfer"}

required = float(sys.argv[1]) if len(sys.argv) > 1 else 100.0
cov = json.load(open("coverage.json"))["files"][FILE]
tree = ast.parse(pathlib.Path(FILE).read_text())

executed, missing = set(cov["executed_lines"]), set(cov["missing_lines"])
missing_branches = [tuple(b) for b in cov.get("missing_branches", [])]
all_branches = cov.get("executed_branches", []) + cov.get("missing_branches", [])

stmts = miss_stmts = branches = miss_branches = 0
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in FUNCS:
        lo, hi = node.lineno, node.end_lineno
        in_fn = lambda n: lo <= n <= hi
        s = {n for n in executed | missing if in_fn(n)}
        m = {n for n in missing if in_fn(n)}
        b = [x for x in all_branches if in_fn(x[0])]
        mb = [x for x in missing_branches if in_fn(x[0])]
        stmts += len(s); miss_stmts += len(m); branches += len(b); miss_branches += len(mb)
        print(f"{node.name:26s} statements {len(s) - len(m)}/{len(s)}  branches {len(b) - len(mb)}/{len(b)}")

total = stmts + branches
covered = total - miss_stmts - miss_branches
pct = 100.0 * covered / total if total else 0.0
print(f"Transfer logic coverage (statements + branches): {pct:.1f}% (required {required:.1f}%)")
sys.exit(0 if pct >= required else 1)
