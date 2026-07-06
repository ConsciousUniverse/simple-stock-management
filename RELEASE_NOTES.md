# Release Notes

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
