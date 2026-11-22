# Waherhous stock management — repository notes

Orascom Construction (أوراسكوم) warehouse app. Django 6.1.3 + DRF, SAP-Fiori-style
UI (Arabic RTL / English LTR), deployed on Render as `ssm-warehouse`
(`https://ssm-warehouse.onrender.com`). Android app consumes the same API.

## Running it locally

`ssm/settings.py` requires several env vars — a bare `manage.py` fails:

```bash
export DJANGO_DEBUG=True ALLOW_PW_CHANGE=False DJANGO_SECRET_KEY=dev-secret \
       DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1 \
       AXES_FAILURE_LIMIT=50 AXES_COOLOFF_TIME=1 LOG_FILE=/tmp/dev.log \
       DB_NAME=dev.sqlite3
python manage.py migrate --run-syncdb --fake-initial --noinput
python manage.py runserver 127.0.0.1:8911 --noreload
```

- `DJANGO_DEBUG=False` turns on `SECURE_SSL_REDIRECT`, so a browser against the
  plain-HTTP dev port fails with `ERR_SSL_PROTOCOL_ERROR`. Use `True` locally.
- Templates/static changes are **not** picked up by a `--noreload` server that was
  started before the edit — restart it before measuring or screenshotting
  (this bit twice: a CSS/template edit "did nothing" until the restart).

## Migrations and the live database

- `migrations/` used to be gitignored, so the live database has **no
  `stock_manager` rows in `django_migrations`**; its tables were created by
  `--run-syncdb`. A new column can only arrive through a migration, so the
  directory is now committed.
- The Render build therefore runs
  `python manage.py migrate --run-syncdb --fake-initial --noinput`:
  `--fake-initial` records `0001_initial` as applied instead of trying to CREATE
  tables that already exist, and later migrations still run.
  **Verified** against a database built from the previous release: `0001 FAKED`,
  `0002 OK`, existing rows kept with an empty unit.
- Never put a `#` comment inside the folded `buildCommand: >-` YAML block — it
  becomes literal shell text and comments out the rest of the command. Put notes
  above the key.
- `--run-syncdb` creates **new tables** only; it never alters an existing one.

## Unit of measure (وحدة القياس)

`Item.unit` + `StockDocumentLine.unit` (+ `GoodsReceiptLine.unit`), free text with
suggestions (`COMMON_UNITS` in `documents.py`). Rules that the tests pin:

- a line that states no unit inherits the item's,
- an addition for an unknown SKU **teaches** the new item its unit,
- a booked line is a snapshot: changing the catalogue later never rewrites it,
- the unit is shown on stock/site tables, the issues list, the report screen and
  the Excel `Unit` column.

## Tests

`python -m pytest -q tests/` — 392 pass, 3 skip (a user-supplied, gitignored
`spreadsheet_convert.py`). `pip install Pillow` and
`python -m playwright install chromium` are needed for the full run; the e2e
suites skip themselves when Chromium is missing.

## Git / push

`$GITHUB_TOKEN` in this sandbox is a `ghu_` OAuth token with read-only access:
`git push` returns `403 Permission … denied` even though `/repos/...` reports
`permissions.push: true`. `$OH_GIT_CREDENTIAL_ACCESS_TOKEN_GITHUB` is invalid
(401). A fresh user-issued `ghp_` token with `repo` scope is required to push and
open a PR.

## One menu, five pages (users, Android app, audit log, label picker)

The sidebar used to differ per shell: the dashboard listed four pages, every
other page listed five, and the two sets overlapped. It is now **nine entries
from one partial** (`templates/partials/sidenav.html`), included by both shells,
with the current entry chosen by URL name in `stock_manager/context.py`
(`NAV_SECTIONS`). A new page means one entry in `NAV_SECTIONS` and one line in
the partial — never a copy per shell.

- **A `{# … #}` comment is single-line in Django.** A multi-line one is *not* a
  comment: it is printed as text on the page. Use `{% comment %}`.
- **`_()` at module level freezes the language.** `ROLE_LABELS` is built at
  import time, so its `_()` calls captured English for every request — the
  Arabic UI showed "Warehouse manager". Module-level labels need `gettext_lazy`.
- **The shellbar states the reader's role**, so `is_manager` is supplied by the
  context processor now: a page whose view forgot to pass it showed "Site user"
  to a manager. Views may still override it.
- **Dates stay left-to-right** (`<td dir="ltr">`): in an RTL page a bare
  `2026-11-21 15:41` is re-ordered into `15:41 2026-11-21`.
- **The dashboard keeps its in-page jump list**, but under «أقسام هذه الصفحة»
  and styled quieter (`.sap-sidenav__nav--sections`), so it does not read as a
  second site menu.
- **Roles are named, not exposed**: `managers`/`shop_users`/`receive_mail` show
  as Warehouse manager / Site user / Mail receiver, and a group added later
  still shows under its own name.
- **The audit log records what a person can read**: sign-in, sign-out, refused
  sign-in, document decisions, password changes (including a self-service one,
  via `AuditedPasswordChangeView`), and a setting change written as
  «Edit lock: on/off» rather than `edit_lock=False`.
- `python -m pytest -q` — 473 pass, 3 skip.

## A deploy onto a database older than the migrations (the "already exists" build)

The first deploy of this branch died in the build:

```
django.db.utils.ProgrammingError: relation "stock_manager_admin" already exists
```

- **`--fake-initial` only looks at the top level of a migration.** It fakes an
  initial migration when every `CreateModel` table **and** every `AddField`
  column already exists; anything else (`AddIndex`, `AlterUniqueTogether`) is
  ignored. The live database was built by `--run-syncdb` at several points in the
  project's life, so one table or column added later was missing — the check
  returned False, Django fell back to creating everything, and the first table it
  tried was already there.
- **Do not chase the flag.** The fix is for the migrations to *adopt* the schema:
  `stock_manager/migrations/_adopt.py` → `ensure_models()` creates a table only
  when it is absent and adds only the columns a table lacks. Each migration wraps
  its state operations in `SeparateDatabaseAndState(state_operations=[…],
  database_operations=[RunPython(adopt…)])`, so the recorded state stays exact
  and the database work is idempotent. That is why the build now works with or
  without `--fake-initial` — worth knowing, because the Render dashboard may hold
  its own copy of the build command.
- **0002 is state-only on purpose**: its `unit` columns are created by 0001's
  adoption step, so a real `AddField` would fail with "duplicate column" on a
  database that already has them.
- **`python manage.py makemigrations --check --dry-run` must still say
  "No changes detected"** after such a change — the state is what the models
  describe, only the DDL is conditional.
- **Reproduce it locally instead of guessing**: build a database from the code
  that predates the migrations (`git worktree add /tmp/old 88ff826`, then
  `migrate --run-syncdb`), drop one table and one column, and run the current
  `migrate`. Before the fix this prints the production error; after it, the table
  and column come back and the audit tables are created.
- **Guard**: `tests/test_migrations_adopt_existing_db.py` (4 tests) drives
  `manage.py migrate` in a subprocess against a real SQLite file. Two of them
  fail against the previous migrations, so they guard the behaviour rather than
  the code path.

## The shell, the pages and the scripts have one definition each

The dashboard used to be a 1,900-line template that re-implemented the sidebar,
the item tables and the label picker, while `stock.html`, `receipts.html` and
`issues.html` carried their own copies of the same markup. The result was the
defect class this repository keeps recording: the same fact stated twice, and
the copies drifting.

- **`stock_manager/navigation.py` is the only menu.** `NAV_GROUPS` holds the
  order, the group titles, the icon and the manager-only flag; `URL_SECTIONS`
  maps a URL name to the entry key, so the active entry follows the page being
  rendered instead of a value each view must remember to pass. A test asserts
  `reverse(url_name) == url` for every entry, so the menu cannot point at a
  route that moved.
- **`templates/partials/sidenav.html` renders it once**, and only
  `base_app.html` includes that partial. A page that renders its own menu is a
  second definition — `tests/test_navigation.py` fails if one appears.
- **`stock_manager/permissions.py` is the only role check.** `is_warehouse_manager`
  replaced a dozen copies of `groups.filter(name="managers").exists()`; the group
  name is spelled once.
- **`stock_manager/ordering.py` is the only table ordering.** Three viewsets had
  byte-identical branches (natural sort on the code, numeric sort on quantities,
  case-insensitive text, stable default). `tests/test_ordering.py` drives the
  helper and then asserts the branches are gone from `views.py`, because a
  helper nobody calls fixes nothing.
- **The dashboard is an overview, not a second copy of the items page**: KPI
  tiles, the site-request queue, and quick links. The tables that do the work
  live on `/stock/`, `/receipts/`, `/issues/` and `/labels/`. The E2E test
  `test_the_dashboard_is_an_overview_not_a_second_copy` fails if the item tables
  come back.
- **`stock_manager/ui_strings.py` had two string maps.** `JS_STRINGS`/`js_strings()`
  were dead once the dashboard stopped being the whole app (nothing imported
  them) while `JS_TEXTS`/`js_messages()` are the live ones: the second map reads
  the `.po` catalog of the active language, so a template message is translatable
  from the script with no second list. Deleting the dead map is safe because the
  catalog is collected from templates, not from that dict.
- **Page scripts live in `stock_manager/static/js/warehouse.js`** (tracked, loaded
  by `base_app.html` after jQuery). It was never in git before this refactor —
  the script was inline in `index.html` — so a static-file check that passes
  locally can still 404 in production if the file is not committed.
- **`sap-msgstrip-error` vs `sap-msgstrip--error`**: the shell template emitted
  the single-dash class for error messages while the stylesheet defines the BEM
  double-dash one, so an error rendered unstyled. Any modifier class in
  `base_app.html` must match `ssm-sap.css`.
- **Printing the label sheet opens a new tab** (`target="_blank"` on the picker
  form): navigating away from the picker to a print page loses the selection the
  operator just made.

## Missing paperwork: one page that is also the place you fix it

The operator's rule is a loop, not a report: every line that moved without its
document is listed **until it is completed from the list**, then it disappears.

- **One row per LINE, never per document.** `stock_manager/reconciliation.py`
  builds rows from `StockDocument` lines and from `GoodsReceipt` lines, so a
  ten-line order with one undocumented line shows one row. A guard
  (`test_a_multi_line_document_shows_one_row_per_line`) fails if the loop is
  collapsed to one row per document.
- **Four reasons, each a real gap**: a pending issue (the issues report reads
  APPROVED only, so it can never appear there), a pending addition (the stock was
  never increased), an approved document with no voucher, and a delivery booked
  by the receipts screen — which writes no stock document at all — with no
  voucher.
- **A delivery covered by a proper addition is not listed.** Otherwise booking
  the addition the normal way would leave the delivery on the page forever and
  report the same goods twice. The coverage lookup is scoped to the orders on the
  page (a page load must not walk every addition ever booked); it can only ever
  miss a coverage (a duplicate row), never hide a real gap.
- **Completing is one transaction**: `record_permit(..., approve=True)` approves
  the document (moving the stock) and writes the voucher together, so a document
  can never carry paper for a movement that did not happen. The docstring said
  this before the code did — fix the code, not the sentence.
- **A voucher is booked once across documents AND deliveries** (`_assert_permit_free`
  plus unique indexes on both `external_ref` columns). The check is the message;
  the index is the referee.
- **`GoodsReceipt.external_ref` is optional on purpose**: the goods are on the
  shelf either way, and a delivery that cannot be paid is exactly what this page
  exists to chase.
- **Short labels for the table, long sentences for the filter and the export.**
  A full sentence in a pill squeezed the columns beside it and pushed the voucher
  input out of view; the sentence is now a `title` tooltip.
- **The page URLs are built once in the view** (`next_url`, `export_url`,
  `page_url_prefix`), so no link can grow a stray `?` or lose the filters.
- **The Arabic catalog is collected by globbing every module.** The old
  hand-kept list omitted `navigation.py`, so the sidebar group titles
  («Operations» / «Administration») had shipped in English on the Arabic
  interface and nothing complained. `scripts/build_messages.py` now scans every
  `stock_manager/*.py`.
- **Verify in a real browser, in both directions**: the loop was checked live
  (row listed → voucher saved → banner «Voucher recorded on …» → row gone, count
  16 → 15) and the Arabic RTL layout was checked by setting the
  `django_language` cookie, since the language switcher is a POST form.
