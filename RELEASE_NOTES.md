# Release Notes

## v6.2.1 — 2026-11-23

The scanning screen, fixed where it was wrong: the phone stayed upright, and
the camera kept looking for focus.

**The phone no longer turns sideways to scan.** The barcode library's own
capture screen is declared `sensorLandscape`, so tapping "scan" rotated a phone
the operator was holding upright — and every rotation restarts the camera. The
app now has its own capture screen, locked to portrait.

**Scanning stops waiting for a lucky frame.** The default is a single autofocus
attempt; when it misses on a cheap phone nothing ever refocuses, so the label
has to be moved back and forth. Focus is now continuous, the barcode scene mode
is on, and the torch lights up by itself in a dark aisle.

**Android 1.4.1 (build 6).** Everything else is unchanged.

## v6.2.0 — 2026-11-23

Three rules that were asked for and are now enforced in the code, not in a
habit.

**One account, one phone.** The first phone that signs in claims the account.
A second phone is refused with a sentence that names the phone holding it, and
a manager frees the account from **/android/ → مستخدمو التطبيق → مسح الجهاز**.
Clearing also stops the token the old phone is still holding, so a lost phone
stops working at once instead of when its token expires.

**Never issue more than the shelf.** The phone refuses a scan that asks for
more than the stock on hand, and the server refuses the same document if the
shelf emptied between submission and approval — the approval moves the balance
through a conditional update, so two approvals can never oversell.

**The app wakes the server instead of failing.** Render stops an idle service
after fifteen minutes; the first request after that used to look like a broken
app. The client now retries with backoff and says «بيتم تشغيل الخادم…» while it
waits.

**Android app 1.4.0 (build 5)**

- **The sign-in screen asks for one thing: the password.** The account stays on
  the phone it was opened on, so the number is no longer retyped every morning.
  «الدخول بحساب آخر» shows the identifier field when a different person uses the
  phone.
- **A dashboard instead of a settings list**: the person, the two actions
  (صرف / إضافة) as full-width tiles, and one line saying how many documents are
  waiting for a manager.
- **The gear** now holds the account, the app version, the manual update check,
  a connection test and the way out — the daily screen stays two buttons.
- **The shelf is visible while you scan**: every line shows «المتاح: 100 متر»,
  turns red past it, and the review button refuses to continue.

## v6.1.0 — 2026-11-22

The warehouse app can now carry a signed paper voucher end to end: the operator
fills in the paper's header, photographs the sheet, scans every item, reviews the
document, and sends it. Nothing moves in the balance until a warehouse manager
approves it on the web.

**Android app 1.3.0 (build 4)** — sign in with a user name or phone number and a
password, then:

1. **Issue (صرف)** or **Add (إضافة)** — the two directions of the same sheet.
2. **Date, document number, where it will be used, the engineer who signed** —
   the header of the paper, typed once.
3. **Photograph the document** — the signed sheet itself, attached to the
   document and stored in the database (not on the server's disk, which a
   deployment wipes).
4. **Scan each item's barcode** — the label resolves to the catalogue article,
   and the line carries **the catalogue's unit**, not one typed on the phone.
   Scanning the same label twice raises the quantity instead of adding a line.
5. **Review page** — the header, the photograph and every line with its unit,
   then one button: صرف or إضافة.
6. **My documents** — what happened to each one: waiting, approved, or rejected
   with the manager's note.

**Web**

- **`/issues/` and `/receipts/` now carry their own approval queue** — each page
  lists the documents waiting on it (issues on Issues, additions on Additions)
  with Review / Approve / Reject beside each row.
- **A document review page** (`/documents/<id>/`) shows the voucher fields, the
  photographed sheet, the lines with their units and the stock on hand, and
  approves or rejects with a note. Approval moves the stock exactly once; the
  same voucher number cannot move it twice.
- **The unit of measure is the catalogue's.** The phone reports the code and the
  quantity; the server decides the unit, so a line can never disagree with the
  article it names.
- **A scanned code is forgiving**: `cbl 3x25`, `CBL 3X25` and `CBL-3X25` all
  find the same article, while an unknown code is refused by name instead of
  being created silently.
- Arabic translations for the whole flow.

**Tests** — 33 new server tests for the mobile document flow (submission,
photograph, unit, voucher booked once, pending moves nothing, approval moves the
stock, rejection, review page access, queue links) and 15 new Android unit tests
for the draft rules and the server payloads. 764 server tests pass.


## v5.3.0-beta — 2026-07-06

This release adds a full automated test suite, fixes a batch of functional
bugs surfaced by that suite, and completes a focused security review whose
findings have all been fixed. It introduces no new runtime dependencies; the
test tooling is a development-only dependency.

> **Versioning note:** this version number was chosen to signal a significant
> security-and-testing milestone. Adjust it to your own scheme if preferred.

### Security

A focused security review was carried out for this release. All identified
issues have been fixed, and several defence-in-depth measures added. This is
not a substitute for a professional third-party audit — continue to deploy
with the precautions in the README.

- **Stored cross-site scripting (XSS) — fixed.** Item SKUs and descriptions
  (and shop usernames) were rendered into the dashboard without escaping, so a
  hostile value stored in the database executed as script in the browser of
  every user who viewed it. All server-supplied values are now HTML-escaped on
  render, and the transfer/delete action buttons no longer build inline
  `onclick` handlers from the SKU (they use delegated handlers reading data
  attributes).
- **Broken access control on item creation — fixed.** `POST /api/items/` had
  no manager check (unlike update and delete), letting any authenticated user
  create or silently reactivate warehouse items. It is now restricted to the
  `managers` group.
- **Insecure direct object reference (IDOR) on transfer cancellation — fixed.**
  The complete-transfer endpoint trusted the `shop_user_id` in the request
  body, so a shop user could cancel another user's pending transfer.
  Non-managers may now only cancel their own transfers.
- **Excel/CSV formula injection on export — fixed.** Exported spreadsheet
  cells beginning with a formula trigger (`= + - @`) are now neutralised so
  they are not executed when a manager opens the downloaded file.
- **HTTPS/cookie hardening added.** When `DEBUG` is off, the app now sets
  `Secure` session and CSRF cookies, `SESSION_COOKIE_HTTPONLY`, HSTS,
  `SECURE_SSL_REDIRECT`, and content-type nosniff, and trusts the reverse
  proxy's `X-Forwarded-Proto` header (`SECURE_PROXY_SSL_HEADER`). See the
  upgrade notes below.
- **Content-Security-Policy added.** A new middleware
  (`ssm.middleware.ContentSecurityPolicyMiddleware`) sets a CSP that
  allow-lists script/style sources to the app's own origin and the jQuery /
  Bootstrap CDNs, restricts outbound connections to same-origin, and forbids
  `eval`/WebAssembly. As defence-in-depth this blocks an injected payload from
  loading an external cryptominer or malware script and from exfiltrating data
  to an external server.
- **Read-only stock/transfer API — hardened.** The `shop_items` and
  `transfer_items` endpoints are now read-only (stock is only ever moved via
  the dedicated transfer/complete endpoints), removing unused write verbs.

A follow-up review pass added further defence-in-depth:

- **API error messages no longer leak internals.** The transfer, submit and
  complete-transfer endpoints returned the raw text of any caught exception,
  so an unexpected internal error could disclose implementation detail
  (CWE-209). Unexpected errors are now logged server-side and answered with a
  generic message; intentional business-rule messages (e.g. "Not enough
  stock") are unchanged.
- **Notification email output escaped.** Item SKU/description and the
  requesting user's name and email are now HTML-escaped in the notification
  email body, preventing markup injection into the message sent to managers
  (CWE-116).
- **Dashboard greeting escaped.** The username shown in the header greeting was
  interpolated via `.html()` without escaping; it is now escaped, consistent
  with the rest of the frontend.

### Fixed

- **Brute-force lockout was global.** The django-axes lockout keyed on a
  deliberately-nulled client IP as well as username, so three failed logins by
  anyone locked out every user. Lockout is now per-username.
- **Single-sheet spreadsheet uploads.** A workbook containing only a
  "Warehouse Stock" or only a "Shop Stock" sheet now imports correctly instead
  of returning an error, and per-sheet deletions no longer touch data governed
  by the absent sheet.
- **Unstable pagination.** The shop-item and transfer-item lists now have a
  deterministic default ordering, so rows no longer shift between pages.
- **Transfer request robustness.** A missing or non-string transfer quantity
  now returns a clean validation error instead of a 500, and a JSON numeric
  quantity is accepted.
- **Fresh-install crashes.** The app configuration accessors no longer raise
  when the configuration row does not yet exist (e.g. immediately after
  install); they fall back to defaults.
- **Edit-lock status endpoint.** `GET /api/get_edit_lock_status/` now requires
  authentication (it was open and CSRF-exempt).
- **Pagination page size.** The page size is now capped at the configured
  maximum and falls back sanely for invalid or non-positive values.
- **Email notifications.** An empty recipient address no longer aborts the
  whole notification send.
- **Logging config.** Removed a duplicate logging handler definition in
  settings.
- **Transfer dispatch quantity/stock integrity.** Dispatch now requires a
  positive integer quantity (a negative value previously inflated warehouse
  stock), and the warehouse decrement is a single atomic conditional update,
  so concurrent dispatches cannot oversell.
- **Removed a dead API endpoint.** The unused `auth/token/` token-auth
  endpoint (token authentication was never configured) has been removed.

### Added — automated tests

- A full **pytest** suite covering models, serializers, pagination, the REST
  API and permissions, the transfer lifecycle, Excel import/export and the
  custom-schema converter, the email service, authentication and lockout, and
  the management commands.
- **Playwright** browser-based end-to-end tests driving the real jQuery
  frontend (login, search, the transfer request/dispatch/cancel flow,
  maintenance mode) plus explicit XSS and CSP regression tests.
- New development dependencies: `pytest`, `pytest-django`, `pytest-playwright`.

### Upgrade notes for deployers

- **No new runtime dependencies.** Deploying with `pipenv install --deploy`
  (without dev packages) requires no changes.
- **Behind a reverse proxy (production, `DEBUG=False`):** the app now enables
  `SECURE_SSL_REDIRECT` and `Secure` cookies and reads
  `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`. Ensure your
  TLS-terminating proxy sets/forwards `X-Forwarded-Proto: https`, otherwise
  you may see redirect loops or cookies that fail to set.
- **Content-Security-Policy:** the policy allow-lists the jQuery and Bootstrap
  CDN hosts used by the templates. If you change those CDN URLs, update
  `CONTENT_SECURITY_POLICY` in `ssm/settings.py` to match, or the resources
  will be blocked.
- **CSRF cookie is intentionally readable by JavaScript** (not `HttpOnly`),
  because the frontend reads the token from it — this is by design, not a
  regression.

### Running the tests

```bash
pipenv install --dev
pipenv run playwright install chromium   # one-time, for the browser tests
pipenv run pytest                        # full suite (includes browser e2e)
pipenv run pytest -m "not e2e"           # backend only, no browser needed
```
