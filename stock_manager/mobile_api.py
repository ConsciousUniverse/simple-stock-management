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

from . import documents as stock_documents
from . import mobile
from .models import StockDocument
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
                device_id=payload.get("deviceId") or payload.get("device_id") or "",
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




# ---------------------------------------------------------------- documents
# The warehouse flow the site user runs on the phone: photograph the signed
# voucher, say where the goods go and who signed it, then scan the items. The
# document is created PENDING — nothing moves until a manager approves it on the
# web, which is the rule ``stock_documents`` exists to enforce.


def _iso_date(raw, label):
    """A date the operator chose, or today when the field is empty."""
    from datetime import date

    text = (raw or "").strip()
    if not text:
        return date.today()
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise mobile.MobileError(f"{label} غير صحيح. استخدم التاريخ بصيغة 2026-11-21.")


def _item_payload(item):
    return {
        "code": item.sku,
        "description": item.description,
        "unit": item.unit or "",
        "quantity": item.quantity,
        "price": str(item.retail_price),
    }


def _document_payload(document, with_lines=True):
    payload = {
        "id": document.pk,
        "number": document.number,
        "direction": document.direction,
        "status": document.status,
        "statusLabel": document.get_status_display(),
        "typeLabel": document.get_doc_type_display(),
        "documentDate": document.document_date.isoformat()
        if document.document_date
        else "",
        "location": document.location,
        "engineerName": document.engineer_name,
        "voucher": document.external_ref or "",
        "notes": document.notes,
        "hasPhoto": bool(document.photo),
        "quantity": document.total_quantity,
        "createdAt": document.created_at.isoformat(),
        "decisionNote": document.decision_note,
    }
    if with_lines:
        payload["lines"] = [
            {
                "code": line.sku,
                "description": line.description,
                "quantity": line.quantity,
                "unit": line.unit,
            }
            for line in document.lines.all()
        ]
    return payload


class ItemLookupView(MobileView):
    """What a scanned label means: the item, its description and ITS unit.

    The unit is the catalogue's, never the phone's guess — an issue counted in
    metres must not become pieces because a screen defaulted to pieces.
    """

    def get(self, request):
        try:
            self.session(request)
            code = (request.GET.get("code") or "").strip()
            if not code:
                raise mobile.MobileError(
                    "امسح الباركود أو اكتب كود الصنف.", code="code_required"
                )
            item = stock_documents.find_item_by_code(code)
            if item is None:
                raise mobile.MobileError(
                    f"الكود {code} غير مسجَّل في المخزن.",
                    status=404,
                    code="item_unknown",
                )
            if not item.is_active:
                raise mobile.MobileError(
                    f"الصنف {item.sku} موقوف ولا يمكن صرفه.",
                    status=409,
                    code="item_inactive",
                )
        except mobile.MobileError as exc:
            return _error(exc)
        return JsonResponse(
            {"item": _item_payload(item)}, json_dumps_params={"ensure_ascii": False}
        )


class DocumentsView(MobileView):
    """The site user's own documents: submit one, and read what happened to it."""

    def get(self, request):
        try:
            session = self.session(request)
        except mobile.MobileError as exc:
            return _error(exc)
        documents = (
            StockDocument.objects.filter(created_by=session.user)
            .prefetch_related("lines")
            .order_by("-created_at", "-id")[:50]
        )
        return JsonResponse(
            {"documents": [_document_payload(doc) for doc in documents]},
            json_dumps_params={"ensure_ascii": False},
        )

    def post(self, request):
        try:
            session = self.session(request)
            payload = _document_input(request)
            document = stock_documents.create_document(
                doc_type=payload["doc_type"],
                lines=payload["lines"],
                location=payload["location"],
                counterparty="",
                reference=payload["voucher"],
                external_ref=payload["voucher"],
                notes=payload["notes"],
                created_by=session.user,
                source=StockDocument.MOBILE,
                pending=True,
                document_date=payload["document_date"],
                engineer_name=payload["engineer_name"],
                photo=payload["photo"],
                photo_type=payload["photo_type"],
                photo_name=payload["photo_name"],
            )
        except stock_documents.DocumentError as exc:
            return _error(mobile.MobileError(str(exc), code="document_refused"))
        except mobile.MobileError as exc:
            return _error(exc)
        return JsonResponse(
            {
                "ok": True,
                "document": _document_payload(document),
                "message": (
                    f"أُرسل المستند {document.number} للمراجعة. "
                    "لا يتغير الرصيد قبل اعتماد مدير المخزن."
                ),
            },
            status=201,
            json_dumps_params={"ensure_ascii": False},
        )


def _document_input(request):
    """Read the multipart submission (or a JSON one, for a test client)."""
    if request.content_type and request.content_type.startswith("multipart/"):
        data = request.POST
        upload = request.FILES.get("photo")
        photo = upload.read() if upload else b""
        photo_type = getattr(upload, "content_type", "") if upload else ""
        photo_name = getattr(upload, "name", "") if upload else ""
        lines_raw = data.get("lines") or "[]"
        try:
            lines = json.loads(lines_raw)
        except json.JSONDecodeError:
            raise mobile.MobileError("تعذّر قراءة بنود المستند.", code="bad_lines")
    else:
        data = _body(request)
        photo = b""
        photo_type = ""
        photo_name = ""
        lines = data.get("lines") or []

    direction = str(data.get("direction") or "").strip().lower()
    if direction not in {StockDocument.IN, StockDocument.OUT}:
        raise mobile.MobileError(
            "حدّد نوع الحركة: صرف أو إضافة.", code="direction_required"
        )
    doc_type = (
        StockDocument.SITE_ISSUE if direction == StockDocument.OUT else StockDocument.SITE_RETURN
    )

    voucher = str(data.get("voucher") or "").strip()
    if not voucher:
        raise mobile.MobileError("اكتب رقم المستند.", code="voucher_required")
    location = str(data.get("location") or "").strip()
    if not location:
        raise mobile.MobileError(
            "اكتب مكان الاستخدام أو التركيب.", code="location_required"
        )
    engineer = str(data.get("engineerName") or data.get("engineer") or "").strip()
    if not engineer:
        raise mobile.MobileError(
            "اكتب اسم المهندس الذي وقّع الطلب.", code="engineer_required"
        )

    if not isinstance(lines, list) or not lines:
        raise mobile.MobileError("أضف صنفًا واحدًا على الأقل.", code="lines_required")

    checked = []
    for raw in lines:
        if not isinstance(raw, dict):
            raise mobile.MobileError("بند غير صالح في المستند.", code="bad_line")
        code = str(raw.get("code") or raw.get("sku") or "").strip()
        if not code:
            continue
        item = stock_documents.find_item_by_code(code)
        if item is None:
            raise mobile.MobileError(
                f"الكود {code} غير مسجَّل في المخزن؛ راجع الملصق أو اكتب الكود يدويًا.",
                status=404,
                code="item_unknown",
            )
        if not item.is_active:
            raise mobile.MobileError(
                f"الصنف {item.sku} موقوف ولا يمكن صرفه.",
                status=409,
                code="item_inactive",
            )
        try:
            quantity = int(str(raw.get("quantity")))
        except (TypeError, ValueError):
            raise mobile.MobileError(
                f"كمية الصنف {item.sku} يجب أن تكون عددًا صحيحًا.", code="bad_quantity"
            )
        if quantity <= 0:
            raise mobile.MobileError(
                f"كمية الصنف {item.sku} يجب أن تكون أكبر من صفر.", code="bad_quantity"
            )
        checked.append(
            {
                "sku": item.sku,
                "quantity": quantity,
                "description": item.description,
                # The catalogue's unit, never one sent by the phone.
                "unit": item.unit or "",
            }
        )

    stock_documents.check_photo(photo, photo_type, photo_name)

    return {
        "doc_type": doc_type,
        "lines": checked,
        "voucher": voucher,
        "location": location,
        "engineer_name": engineer,
        "notes": str(data.get("notes") or "").strip(),
        "document_date": _iso_date(
            data.get("documentDate") or data.get("document_date"), "تاريخ المستند"
        ),
        "photo": photo,
        "photo_type": photo_type,
        "photo_name": photo_name,
    }



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
