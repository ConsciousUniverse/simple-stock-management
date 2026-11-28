"""
Custom mutation operators for the decorated rule functions that mutmut skips
(transfer_item, complete_transfer, submit_transfer_request).

Operators (each is derived from a business rule):
  LIMIT_BOUNDARY      R1 boundary:   "<= 0"  ->  "< 0"
  LOCK_NEGATE         R2 decision:   Admin.is_edit_locked()  ->  not Admin.is_edit_locked()
  PERMISSION_FLIP     R4 permission: "not is_manager" -> "is_manager",
                                     "shop_user != request.user" -> "==",
                                     "not <group>.exists()" -> "<group>.exists()"
  CANCEL_FLAG_FLIP    R3 state:      cancel == "true"  ->  cancel != "true"
  STATE_ORDERED_FLIP  R3 state:      ordered=True/False literal is inverted

Usage (from repo root, venv active):  python scripts/custom_mutants.py
Writes docs/evidence/custom_mutants_report.md
"""
import ast
import copy
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "stock_manager" / "views.py"
TARGETS = {"transfer_item", "complete_transfer", "submit_transfer_request"}
DESELECT = ("tests/team/test_transfer_rules.py::"
            "test_candidate_defect_json_boolean_cancel_is_treated_as_cancel")


def _name(n, ident):
    return isinstance(n, ast.Name) and n.id == ident


def op_limit(node):
    if (isinstance(node, ast.Compare) and isinstance(node.ops[0], ast.LtE)
            and isinstance(node.comparators[0], ast.Constant) and node.comparators[0].value == 0):
        node.ops[0] = ast.Lt()
        return node


def op_lock(node):
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "is_edit_locked"):
        return ast.UnaryOp(op=ast.Not(), operand=node)


def op_perm(node):
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        if _name(node.operand, "is_manager"):
            return node.operand
        if (isinstance(node.operand, ast.Call) and isinstance(node.operand.func, ast.Attribute)
                and node.operand.func.attr == "exists"):
            return node.operand
    if (isinstance(node, ast.Compare) and isinstance(node.ops[0], ast.NotEq)
            and _name(node.left, "shop_user")):
        node.ops[0] = ast.Eq()
        return node


def op_cancel(node):
    if (isinstance(node, ast.Compare) and isinstance(node.ops[0], ast.Eq)
            and isinstance(node.comparators[0], ast.Constant) and node.comparators[0].value == "true"):
        node.ops[0] = ast.NotEq()
        return node


def op_ordered(node):
    if (isinstance(node, ast.keyword) and node.arg == "ordered"
            and isinstance(node.value, ast.Constant) and isinstance(node.value.value, bool)):
        node.value = ast.Constant(value=not node.value.value)
        return node


OPS = {
    "LIMIT_BOUNDARY": op_limit,
    "LOCK_NEGATE": op_lock,
    "PERMISSION_FLIP": op_perm,
    "CANCEL_FLAG_FLIP": op_cancel,
    "STATE_ORDERED_FLIP": op_ordered,
}


class Mutator(ast.NodeTransformer):
    def __init__(self, target=None):
        self.target, self.i, self.sites, self.fn = target, 0, [], None

    def visit(self, node):
        if isinstance(node, ast.FunctionDef):
            if node.name in TARGETS:
                self.fn = node.name
                self.generic_visit(node)
                self.fn = None
            return node
        if self.fn:
            for name, op in OPS.items():
                # check applicability on a copy so the original is untouched
                trial = op(copy.deepcopy(node))
                if trial is not None:
                    idx = self.i
                    self.i += 1
                    self.sites.append((idx, name, self.fn, getattr(node, "lineno", 0), ast.unparse(node)[:60]))
                    if idx == self.target:
                        return op(node)
                    break
        return self.generic_visit(node)


def mutate_source(target):
    tree = ast.parse(SRC.read_text())
    m = Mutator(target)
    tree = m.visit(tree)
    return ast.unparse(ast.fix_missing_locations(tree)), m.sites


def run_tests(workdir):
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/team", "-q", "-x", "-p", "no:cacheprovider",
         "--deselect", DESELECT],
        cwd=workdir, capture_output=True, text=True, timeout=300)
    return r.returncode == 0


def main():
    _, sites = mutate_source(None)
    print(f"{len(sites)} mutants generated")
    work = pathlib.Path(tempfile.mkdtemp())
    shutil.copytree(ROOT, work / "p", ignore=shutil.ignore_patterns(
        ".git", "mutants", ".venv", "__pycache__", "node_modules", "docs"))
    proj = work / "p"
    target_file = proj / "stock_manager" / "views.py"
    original = SRC.read_text()
    target_file.write_text(ast.unparse(ast.parse(original)))
    assert run_tests(proj), "baseline (unmutated, re-printed source) must pass"
    rows, killed = [], 0
    for idx, name, fn, line, snippet in sites:
        src, _ = mutate_source(idx)
        target_file.write_text(src)
        ok = run_tests(proj)
        status = "SURVIVED" if ok else "killed"
        killed += not ok
        rows.append((idx, name, fn, line, snippet, status))
        print(f"{idx:3d} {name:20s} {fn:24s} L{line:<4d} {status}")
    total = len(sites)
    out = ROOT / "docs" / "evidence" / "custom_mutants_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Custom mutation operators report", "",
             f"Mutants: {total}, killed: {killed}, survived: {total - killed}, "
             f"score: {killed / total:.0%}", "",
             "| # | Operator | Function | Line | Original code | Result |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | `{r[4].replace('|', '/')}` | {r[5]} |")
    out.write_text("\n".join(lines) + "\n")
    print(f"killed {killed}/{total} ({killed / total:.0%}); report: {out}")
    required = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
    sys.exit(0 if 100.0 * killed / total >= required else 1)


if __name__ == "__main__":
    main()
