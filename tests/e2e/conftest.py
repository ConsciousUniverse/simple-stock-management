"""
Fixtures for the Playwright end-to-end suite.

The templates load jQuery and Bootstrap from CDNs; to keep the tests
hermetic those requests are intercepted and served locally (jQuery from the
identical 3.7.1 copy vendored with the Django admin, Bootstrap as a minimal
stub defining the `.d-none` visibility rule the app's logic relies on).
"""

import os
from pathlib import Path

import pytest
from django.conf import settings

# Playwright's sync API keeps an asyncio event loop running in the test
# thread, which trips Django's async-context guard on ORM calls. The test
# code is genuinely synchronous, so the guard can be safely bypassed.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

JQUERY_PATH = (
    Path(settings.BASE_DIR) / "static" / "admin" / "js" / "vendor" / "jquery" / "jquery.min.js"
)
BOOTSTRAP_STUB = ".d-none { display: none !important; }"


@pytest.fixture
def page(page):
    page.route(
        "https://code.jquery.com/**",
        lambda route: route.fulfill(
            path=str(JQUERY_PATH), content_type="application/javascript"
        ),
    )
    page.route(
        "https://cdn.jsdelivr.net/**",
        lambda route: route.fulfill(body=BOOTSTRAP_STUB, content_type="text/css"),
    )
    return page


@pytest.fixture
def login(page, live_server):
    """Log a user in through the real login form and land on the dashboard."""

    def _login(username, password="test-pass-123"):
        page.goto(f"{live_server.url}/accounts/login/")
        page.fill('input[name="username"]', username)
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')
        page.wait_for_url(f"{live_server.url}/")

    return _login


def _chromium_available():
    """True only if Playwright's Chromium binary is actually installed."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:
        # If we can't determine it, don't silently skip — let it behave as
        # before (the browser fixture will error) rather than hide a problem.
        return True


def pytest_collection_modifyitems(config, items):
    """Skip the browser-driven e2e tests when Chromium isn't installed (e.g. on
    a server) so the full suite runs cleanly instead of erroring on launch."""
    e2e_items = [item for item in items if item.get_closest_marker("e2e")]
    if not e2e_items or _chromium_available():
        return
    skip = pytest.mark.skip(
        reason="Playwright Chromium not installed "
        "(run: pipenv run playwright install chromium)"
    )
    for item in e2e_items:
        item.add_marker(skip)
