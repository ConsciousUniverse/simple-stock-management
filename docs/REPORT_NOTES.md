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
## SonarQube results

Run: 2026-11-27, SonarQube Community Build v26.11 (MQR mode), local Docker, scanner sonarsource/sonar-scanner-cli.
Scope: stock_manager, ssm, email_service (migrations and static excluded). Coverage input: coverage.xml from tests/team.
Evidence: docs/evidence/ (screenshots of summary, issues list).

### Metrics (Overall Code)
| Metric | Value |
|---|---|
| Lines of code | 1.7k |
| Quality gate | Passed (default gate; analysis has warnings, details: to add) |
| Security | 3 open issues, rating B |
| Reliability | 2 open issues, rating C |
| Maintainability | 2 open issues, rating A |
| Coverage | 36.5% on 1k lines to cover |
| Duplications | 2.1% on 2.1k lines |
| Security hotspots | 0, rating A (metric marked deprecated) |
| Accepted issues | 0 |
| Technical debt | to add |
| Cyclomatic complexity | to add |

### Findings
3 distinct findings. In MQR mode one finding can count against several qualities, so the
counts above (3 + 2 + 2 = 7) are impact counts, not 7 separate issues.

| # | File, line | Rule | Impact |
|---|---|---|---|
| 1 | email_service/email.py L16 | Don't use pytz with Python 3.9+ | Security Low, Reliability Medium, Maintainability High |
| 2 | stock_manager/utils.py L12 | Don't use pytz with Python 3.9+ | Security Low, Reliability Medium, Maintainability High |
| 3 | stock_manager/views.py L241 | Explicitly specify the HTTP methods this endpoint accepts | Security Low |

### Analysis
1. pytz (findings 1 and 2): pytz is a direct dependency in the Pipfile. Python 3.9+ has the
   built-in zoneinfo module, so pytz is outdated. Risk: wrong results around daylight saving
   if used incorrectly. Fix: replace pytz with zoneinfo. To check: how the two files use it.
   Both files are outside the transfer workflows.
2. HTTP methods (finding 3): line 241 is the index page view. It has login_required and
   ensure_csrf_cookie but does not restrict the HTTP methods. Risk is low because it only
   renders a page. Fix: add require_http_methods(["GET"]).
3. Static analysis found nothing in complete_transfer or the stock rules. It reported no bugs,
   vulnerabilities or hotspots there. My own tests found a logic defect that Sonar did not:
   a JSON boolean cancel flag is treated as a dispatch. Static analysis finds code patterns,
   not wrong business logic.
4. Coverage 36.5% is the whole scanned scope. Coverage of the four transfer functions is
   100% from the team tests. The rest (import/export, serializers, email) is not covered.
5. The default quality gate passed because it checks new code only and this was the first
   analysis. It would not block a pull request with low overall coverage. A custom gate with
   thresholds justified from measured results is needed (CI step).

### Still to add
- Text of the analysis warning (See details)
- Technical debt and complexity values
- Per-file coverage of stock_manager/views.py (Sonar Code tab) compared with coverage report
- Complexity of complete_transfer from SonarQube or radon, compared with hand value 12