"""Unauthenticated liveness probe for the hosting platform."""

from django.http import JsonResponse


def healthz(request):
    """Return 200 as soon as the WSGI app can answer.

    Deliberately does not touch the database: the probe must stay green while a
    migration or a database failover is in progress, otherwise the platform
    restarts a healthy process. Readiness of the data layer is visible on the
    sign-in page instead.
    """
    return JsonResponse({"status": "ok"})
