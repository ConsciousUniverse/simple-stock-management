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
