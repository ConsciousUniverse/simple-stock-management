"""The JSON endpoints the Android app talks to.

Plain Django views rather than DRF: the payloads are small and fixed, the app
authenticates with a bearer token (no cookies, so no CSRF surface), and the
refusals must be readable Arabic sentences the app can show untouched.

Nothing here writes a phone number. ``POST /api/mobile/phone-change-requests/``
creates a REQUEST; the number moves only when a manager approves it in the web
interface, which is what the operator asked for.
"""

import json
import logging

from django.core.cache import cache
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from . import mobile
from .phones import canonical_phone

logger = logging.getLogger(__name__)

#: Failed sign-ins allowed per phone+address before the answer becomes a wait.
LOGIN_ATTEMPT_LIMIT = 10
LOGIN_ATTEMPT_WINDOW_SECONDS = 15 * 60


def _body(request):
    if not request.body:
        return {}
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise mobile.MobileError("تعذّر قراءة الطلب.", code="bad_json")
    if not isinstance(payload, dict):
        raise mobile.MobileError("تعذّر قراءة الطلب.", code="bad_json")
    return payload


def _error(exc):
    return JsonResponse(
        {"error": exc.message, "code": exc.code}, status=exc.status, json_dumps_params={"ensure_ascii": False}
    )


def _client_key(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    address = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
    return address or "unknown"


def _attempt_key(request, phone):
    return f"mobile-login:{canonical_phone(phone)}:{_client_key(request)}"


def _too_many(request, phone):
    return cache.get(_attempt_key(request, phone), 0) >= LOGIN_ATTEMPT_LIMIT


def _count_failure(request, phone):
    key = _attempt_key(request, phone)
    cache.add(key, 0, LOGIN_ATTEMPT_WINDOW_SECONDS)
    try:
        cache.incr(key)
    except ValueError:  # the key expired between add and incr
        cache.set(key, 1, LOGIN_ATTEMPT_WINDOW_SECONDS)


def _bearer(request):
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.lower().startswith("bearer "):
        return ""
    return header.split(" ", 1)[1].strip()


class MobileView(View):
    """Common plumbing: JSON in, JSON out, and a token instead of a session."""

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def session(self, request):
        session = mobile.session_for_token(_bearer(request))
        if session is None:
            raise mobile.MobileError(
                "انتهت الجلسة. سجّل الدخول من جديد.", status=401, code="unauthenticated"
            )
        return session


class LoginView(MobileView):
    def post(self, request):
        try:
            payload = _body(request)
            # A phone number or a user name: both are how people know
            # themselves, and the password is what proves it.
            identifier = (
                payload.get("phone")
                or payload.get("username")
                or payload.get("identifier")
                or ""
            )
            if _too_many(request, identifier):
                raise mobile.MobileError(
                    "محاولات دخول كثيرة. انتظر ربع ساعة ثم حاول.",
                    status=429,
                    code="too_many_attempts",
                )
            result = mobile.login(
                identifier,
                payload.get("password"),
                device=payload.get("device") or "",
                request=request,
            )
        except mobile.MobileError as exc:
            if exc.code in {"bad_password", "phone_unknown"}:
                _count_failure(request, identifier)
            return _error(exc)
        cache.delete(_attempt_key(request, identifier))
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False})


class LogoutView(MobileView):
    def post(self, request):
        try:
            mobile.logout(self.session(request))
        except mobile.MobileError as exc:
            return _error(exc)
        return JsonResponse({"ok": True})


class MeView(MobileView):
    def get(self, request):
        try:
            session = self.session(request)
        except mobile.MobileError as exc:
            return _error(exc)
        return JsonResponse(
            mobile.profile_payload(session.user), json_dumps_params={"ensure_ascii": False}
        )


class PhoneChangeRequestView(MobileView):
    """The app may ASK for a new number. It cannot set one."""

    def post(self, request):
        try:
            session = self.session(request)
            payload = _body(request)
            if "phone" in payload:
                # A client that tries to write the phone directly is refused
                # outright: silently ignoring the field would let it believe
                # the number changed.
                raise mobile.MobileError(
                    "لا يمكن تغيير رقم الهاتف من التطبيق. أرسل طلبًا لمدير المخزن.",
                    status=403,
                    code="phone_locked",
                )
            record = mobile.request_phone_change(
                session.user,
                payload.get("requestedPhone") or "",
                payload.get("reason") or "",
            )
        except mobile.MobileError as exc:
            return _error(exc)
        return JsonResponse(
            {
                "ok": True,
                "request": {
                    "id": record.pk,
                    "requestedPhone": mobile.display_phone(record.requested_phone),
                    "status": record.status,
                },
                "message": "أُرسل الطلب إلى مدير المخزن. لا يتغير الرقم قبل موافقته.",
            },
            status=201,
            json_dumps_params={"ensure_ascii": False},
        )


class VersionView(View):
    """Public: the app must be able to ask before it has signed in."""

    def get(self, request):
        raw = (request.GET.get("code") or "").strip()
        installed = int(raw) if raw.isdigit() else None
        response = JsonResponse(
            mobile.version_payload(installed), json_dumps_params={"ensure_ascii": False}
        )
        response["Cache-Control"] = "no-store"
        return response
