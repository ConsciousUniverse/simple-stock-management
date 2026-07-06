"""
Custom middleware for SSM.
"""

from django.conf import settings


class ContentSecurityPolicyMiddleware:
    """
    Attach a Content-Security-Policy response header from
    settings.CONTENT_SECURITY_POLICY (if set).

    The policy keeps 'unsafe-inline' because the templates use inline event
    handlers and inline styles, so it does not by itself block inline-script
    XSS (output-encoding in the templates handles that). Its job is
    defence-in-depth: the tight script-src / connect-src / object-src rules
    stop an injected payload from loading an external miner or malware script
    and from exfiltrating data to an attacker-controlled host, and the
    absence of 'unsafe-eval'/'wasm-unsafe-eval' blocks eval- and WASM-based
    payloads.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.policy = getattr(settings, "CONTENT_SECURITY_POLICY", None)

    def __call__(self, request):
        response = self.get_response(request)
        if self.policy and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = self.policy
        return response
