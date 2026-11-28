"""
Mutation gate for transfer_to_shop (mutmut results).

Usage: python scripts/check_mutation.py [required_percent]   (default 95)
Run `mutmut run --max-children 1 "stock_manager.views.x_transfer_to_shop*"` first.
"""
import subprocess
import sys

required = float(sys.argv[1]) if len(sys.argv) > 1 else 95.0
out = subprocess.run(["mutmut", "results", "--all", "true"], capture_output=True, text=True).stdout
lines = [l for l in out.splitlines() if "x_transfer_to_shop" in l]
killed = sum(1 for l in lines if l.strip().endswith("killed"))
survived = sum(1 for l in lines if l.strip().endswith("survived"))
total = killed + survived
if total == 0:
    print("No mutants were run: failing the gate.")
    sys.exit(1)
pct = 100.0 * killed / total
print(f"transfer_to_shop mutation score: {killed}/{total} = {pct:.1f}% (required {required:.1f}%)")
sys.exit(0 if pct >= required else 1)
