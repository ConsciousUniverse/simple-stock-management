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

## Company permits (إذن صرف): one issue, several permits, each with its items

The operator's case: an issue dated 1/7 is paid against **three** company
permits (050340604, 0503537228, 05245322) and the report must say **which items
each permit covers**. A company permit is not a second kind of document — it is
a way of covering part of an issue.

- **`DocumentPermit`** (document FK, `permit_no`, `amount`, `note`) plus
  `StockDocumentLine.permit` (`SET_NULL`). A line belongs to **one** permit, so
  the paper trail is a simple FK, not a join table. The permit table sits
  **before** `StockDocumentLine` in `models.py` because the line references it.
- **A permit number is unique across documents** (unique index) and checked in
  code first so the operator gets a sentence naming the other document instead of
  a raw integrity error. The check is the message; the index is the referee —
  the mutation check showed the save still refuses with the check removed,
  because the database refuses it.
- **`stock_manager/permits.py` is the one rule set**: `parse_form` (indexed
  fields `permit_no_<i>` / `permit_amount_<i>` / `items_<i>`, so a permit and its
  items stay together even with a blank row in the middle), `save_permits`
  (update existing rows in place, delete only the rows the operator removed —
  **never delete-and-reinsert**, the lines point at these rows),
  `line_value`/`coverage` (issue value, permits total, difference, uncovered
  lines, `documented`).
- **A comma is a thousands separator or nothing.** The first cut stripped every
  comma, so the Arabic-localised `1250,50` became **125050.00** — a silent 100×
  inflation. `THOUSANDS` accepts `1,250.50` and refuses `1250,50`.
- **A localised number breaks a number input, and the browser then posts an empty
  field.** `{{ row.amount }}` renders `1250,50` in Arabic; `<input type=
  "number">` rejects it and comes back blank, so a plain save **zeroed every
  amount** (found in the browser, not by the tests). The input value must be
  `|unlocalize`; display text uses `format_amount` (`1,250.50` in both
  languages, because an accountant compares this page with the company's paper).
  The guard reads the rendered value back and posts it again — a unit test that
  posts a literal string cannot see this.
- **The report gains a «إذن الصرف» column per line, a permits card (number,
  amount, items, note) and a «صرفيات بلا إذن صرف» table** whose links carry the
  report window as `?next=` (URL-encoded, or the `to` date is lost). The Excel
  export gains a **Company permits** sheet with one row per permit-item, so the
  workbook can be filtered by permit like the page.
- **`permit_missing` in `reconciliation.py` is now per line**: a line the permit
  covers is documented even while the document is split across several permits.
  An issue with **no** permit at all keeps behaving exactly as before, and a
  document voucher (`external_ref`) still documents every line.
- **The difference between the permits total and the issue value is shown, not
  chased.** It is a reconciliation question for the accountant, not a missing
  paper: treating it as a gap would list documents whose paper is complete.
- Tests: `tests/test_document_permits.py` (26) + `tests/e2e/test_permits.py` (3,
  real browser). The guards were each verified to fail with the behaviour
  removed: the per-line permit filter, the cross-document check (the index still
  refuses it — that is the point), the Arabic round-trip save, and the e2e
  round-trip in Arabic (`'' == '1250.50'` — the browser really does empty the
  field).

## The phone app (android/) — number or user name, and updates that arrive

The warehouse is operated from phones, so the app is not a nice-to-have: it is
the second face of the same API (`/api/mobile/*`). Three rules live in
`stock_manager/mobile.py` and nowhere else.

### The number is the manager's, the password is the user's

- `canonical_phone` (`stock_manager/phones.py`) folds every spelling of one
  number — `+20 101…`, `0020101…`, `0101…`, and the copy-pasted form that
  carries an invisible bidi mark (U+2066…) — to `2010…`. Two accounts must never
  be creatable for one number, so the fold is used on **write** as well.
- `login()` accepts a **phone number or a user name** (`resolve_user`). The
  number is tried first; a number that belongs to nobody falls through to the
  user name, so a numeric user name still works. The PHONE stays the identity
  either way — signing in with a user name does not create a second identity.
- The app cannot write the number. `POST /api/mobile/phone-change-requests/`
  only records a `PhoneChangeRequest`; a payload containing `phone` is refused
  with `403 phone_locked`. The manager approves on `/users/`, which is also the
  only place the number is written (`mobile.set_phone`).

### The update decision is a number comparison, made by the app

- `AppRelease.latest()` returns the **highest `version_code`**, not the row
  flagged current. The old version returned the current row, so publishing an
  older build **hid the newer one** — a phone on the older build was told there
  was nothing to install.
- Publishing refuses a build number that does not grow. The message names the
  number, because "the update did nothing" is otherwise indistinguishable from
  "the phones never saw it".
- The app decides, not the server's wording: `Update.parseVersionResponse`
  returns null when there is no build number or no address, and `isNewerThan`
  refuses an equal or lower build. A response claiming an update for the build
  the phone already has must not open a dialog forever.
- The APK is downloaded, its **SHA-256 compared with the published one**, and
  only then handed to the installer through a `FileProvider`. A mismatch is
  deleted and reported; installing it would be installing something else.
- `UpdateWorker` repeats the check every six hours so a phone in a drawer is
  told about a mandatory build; the dialog has no "later" for `mandatory`.

### The APK is hosted, never stored

Render's disk is wiped on every deploy, so `/android/` stores the **address**,
the checksum and the size — never the file. The current builds live in
`melsofany/warehouse-app-releases` (public, releases only).

`android/app/keystore/warehouse-release.jks` is **committed on purpose**:
Android refuses an update signed by a different key, so a per-machine debug key
would force every phone to uninstall before each update. Bump `versionCode` on
every build — a build with the same number is never offered.

### Test what a phone does, not what the server says

`tests/test_mobile_app.py` drives the HTTP API: every spelling of a number
resolving to one account, the lock (a `phone` in the payload is refused and the
stored number is unchanged), approval/refusal, and the build-number decision
including "a release without a build number is not an update".
`android/app/src/test/…/VersionDecisionTest.kt` pins the app's own decision;
a server-side test cannot see a client that installs a downgrade.

## The phone is the whole account, and the app cannot be pointed elsewhere

Two operator asks on `/users/`: an account for a warehouse worker who only has
the phone, and no way to type a server address into the app.

- **`MobileProfile.mobile_only`** is the flag, and `stock_manager/auth.py` is the
  single backend that reads it: `WarehouseBackend` replaces django's
  `ModelBackend` so the web form refuses an app-only account while the app admits
  it (`authenticate(..., app_sign_in=True)`). Two backends would each answer for
  one door and drift; the flag travels with the credential check.
- **The refusal is generic on purpose.** Naming which numbers are app-only tells
  an outsider which numbers to attack, so the sign-in page carries a standing
  line instead («حساب عامل المخزن يعمل على تطبيق الهاتف فقط»). Do not "improve"
  this into a per-account message.
- **Creating the account and its phone is ONE step** (`mobile.create_app_user`):
  a user row created first and given a phone later is an account that exists and
  cannot sign in. The phone is canonicalised (`2010…`, no `+`) because that is
  what the webhook and the app send; the display form adds the `+`.
- **`/users/` gained only what the job needs**: a Door column (app only / web
  and app / web only), Close/Reopen beside Edit, and a two-tab New user card
  (App account / Web account). The tabs are `static/js/users.js` + `.sap-tabs`;
  the JS keys panels off `data-panel`, so a third kind of account is one button
  and one form.
- **The last active manager cannot be closed** (`_is_last_manager`). The deployed
  host has no shell, so that click is an unrecoverable lockout — the same reason
  a manager cannot close their own account.
- **`_toggle_active` rejects a non-numeric id before the query**: `filter(pk="abc")`
  raises `ValueError` and a 500, and the id arrives from a form.

### The app: logo, and an address that cannot be typed

- Icons are generated from `stock_manager/static/img/logo-mark.png` (the raven —
  **not** `company-logo.png`, which is the Orascom wordmark). Legacy
  `mipmap-*/ic_launcher.png` are white rounded tiles with the mark;
  `mipmap-anydpi-v26/ic_launcher.xml` is the adaptive icon (white background,
  `drawable-*/ic_launcher_foreground.png`, plus `monochrome`); `drawable-*/app_logo.png`
  is the mark on the sign-in screen.
- **`Session.baseUrl` is `val = BuildConfig.DEFAULT_BASE_URL`** — no setter, no
  stored copy, and `forgetStoredServer()` deletes the key an older build saved. A
  field that could repoint the app was a way to send a warehouse password to
  another host, and a phone that remembered a typo could not be fixed by the
  person holding it.
- `tests/test_android_sources.py` guards the two promises as text (no
  `serverInput`/`textUri`, the `val baseUrl` line, the icon files, `versionCode >= 2`).
- **Build 2 (1.1.0) is published** to `melsofany/warehouse-app-releases` as
  release `v2` / `warehouse-2.apk`, sha256
  `d2e5e1c317a699b12a534bc00d78af0f674759c6e7e6a0e728e65add07a1c1d5`, 5,726,658
  bytes — verified by downloading the asset back and hashing it.

## Two doors, and a refusal that says which one

A sign-in can be refused for three different reasons that used to produce one
line: a wrong password, an account that is **app-only** (the web form refuses it
by design), and an account that is **closed**. Someone wrote "I cannot sign in"
and nothing on the page answered it.

- **The reason is named only after the password checks out.** `WarehouseBackend`
  sets `request.login_refusal`, and `WarehouseLoginView.form_invalid` replaces
  the "enter a correct username and password" line with it. A wrong password
  still gets the generic message, so the page never tells an outsider which
  accounts exist or which door they use.
- **A closed account is not a wrong password.** `ModelBackend` refuses both with
  `None`; the backend re-checks the password itself before saying "closed", so
  the answer goes to the person who owns the account.
- **The lockout page promised a reset that did not exist.** `axes` locks a
  username after `AXES_FAILURE_LIMIT` failures, and `registration/lockout.html`
  said "ask the system administrator to reset it" — with no reset in the product.
  `stock_manager/lockout.py` is now the one rule: `states()` (ONE query for the
  page), `state()`, `clear()`. `/users/` shows a «مقفول» pill and a «فتح القفل»
  button, and clearing is audited (`user_unlocked`).
- **A lockout is not an error in the account.** The password may be perfect and
  the person still cannot get in; that is exactly what the badge says.
- **The way back in is a deploy variable.** Accounts are created from `/users/`,
  which is the door that is shut when the last manager is locked out or has
  forgotten the password. `reset_user` (also called from `bootstrap_admin`, the
  command already in the build) resets ONE account from `RESET_USER_USERNAME` /
  `RESET_USER_PASSWORD`, reopens it, puts it in `managers` and clears its lockout
  — and does nothing at all when the variables are unset. Anyone who can set
  those can already set `DATABASE_URL`, so it grants nothing new; the reset is
  audited (`user_reset`).
- **A bootstrap account, so the first door is never locked.** `bootstrap_admin`
  (in the build command) creates `sysadmin` in `managers` from a **PBKDF2 hash**
  in `stock_manager/bootstrap_account.py` — the plaintext is not in the repo, and
  changing the password from `/users/` replaces the hash and makes the entry
  inert. It only ever CREATES: an existing account is never touched, so a
  redeploy cannot reset a password set in the UI. Remove the module once the
  owner has their own account.
- **Build lazy strings with their own name.** `views.py` already had
  `gettext as _`; a second `from ... import gettext_lazy as _` was shadowed, so
  the refusal dict was evaluated ONCE under English and the Arabic page showed
  English for every request. Use `_lazy` and assert the rendered text (a test
  now does).

## The update is read from where the builds are, not typed into a page

`/api/mobile/version/` used to answer from the `AppRelease` table, so shipping a
build had **two** steps: publish the release, then remember to record it on
`/android/`. Forgetting the second left every phone on the old build while the
new one sat published and unreachable — and nothing anywhere said so.

- **`stock_manager/releases.py`** reads the release list (`APP_RELEASES_REPO`,
  default `melsofany/warehouse-app-releases`) and returns the newest build **by
  version code**. Publishing a GitHub release IS publishing the update.
- **The number is parsed, not guessed**: `parse_version_code` takes `v2`,
  `warehouse-2.apk` and `Warehouse 1.1.0 (build 2)` as 2, and refuses `1.1.0` —
  a dotted version cannot be ordered, and a wrong number either offers an update
  that is not newer or hides one that is. A release with no readable number is
  still SHOWN on the page (with `versionCode: null`) and never offered.
- **Drafts and pre-releases are never offered**, and a release with no `.apk`
  asset is not a build.
- **The manual row survives as the fallback**, because a phone asking "is there
  an update?" must get an answer during a GitHub outage. A manual row with a
  HIGHER code wins (an explicit pin forward); an older one never hides the
  published build.
- **A failed read is not an absence.** The first cut answered `null` when the
  read failed, so a GitHub refusal and a company with no builds looked identical
  — the phone was told there is nothing to install while a build existed. Every
  successful read is now mirrored into `app_releases` (`source="github"`,
  migration `0008`), a failed read is served from that mirror (`source: "cache"`),
  and the failure is classified (`rate_limited` / `unreachable` / `bad_response`)
  and reported as `releaseError` in the payload and on the page. **An error
  object from GitHub must never be read as `[]`** — that is the same defect in
  a different hat. A mirrored row is excluded from `latest_manual()`, so it can
  never act as a manual pin.
- **One request per ten minutes, shared by every phone** (`CACHE_SECONDS`);
  a failure is remembered for 60s so an outage does not turn into a retry storm.
  The fetch is anonymous (the releases repo is public) and `GITHUB_RELEASES_TOKEN`
  only raises the hourly limit.
- **`tests/conftest.py` stubs the fetch for the whole suite** (`no_live_release_list`):
  without it every test that touches the version endpoint would depend on GitHub
  being up. A test that wants releases patches it deliberately.
- The `/android/` page now shows the build the server actually discovered
  (version, build number, date, size, SHA-256, link) with a card saying the
  update arrives by itself, and the manual form is labelled a fallback. A page
  that shows one build while the app is told about another is the same defect
  class as a log naming an engine that is not running.
