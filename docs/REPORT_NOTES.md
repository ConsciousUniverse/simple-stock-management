## MCC and MC/DC: permission rule in complete_transfer

Source: stock_manager/views.py, lines 429-443.
Conditions:
- M = requester is a manager
- C = cancel flag is the string "true"
- O = target shop user is the requester
Rule: permission granted = M or (C and O)

| Row | M | C | O | Outcome |
|-----|---|---|---|---------|
| 1 | F | F | F | denied (403) |
| 2 | F | F | T | denied (403) |
| 3 | F | T | F | denied (403) |
| 4 | F | T | T | allowed |
| 5 | T | F | F | allowed |
| 6 | T | F | T | allowed |
| 7 | T | T | F | allowed |
| 8 | T | T | T | allowed |

MC/DC pairs (only one condition changes and the outcome changes):
- M: rows 3 and 7
- C: rows 2 and 4
- O: rows 3 and 4
Minimal set: rows 2, 3, 4, 7 (n + 1 = 4 tests).

Tests: tests/team/test_mcc_permission.py (one test per row, ids MCC-row1 to MCC-row8).
Result: 45 passed, 1 failed in 4.99s (run on 2026-11-27, Python 3.13, Windows).
The failure is test_candidate_defect_json_boolean_cancel_is_treated_as_cancel (expected).
Evidence: docs/evidence/2026-11-27_team_tests_45pass_1fail.png