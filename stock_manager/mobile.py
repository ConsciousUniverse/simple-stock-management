"""The Android app's server side: who you are, and which build you should run.

Two rules live here and nowhere else:

* **The phone is written in ONE place** — ``set_phone``, called by a warehouse
  manager from the web. Nothing the app sends can move it; a change is a
  request a manager decides.
* **The update decision is a number comparison** — ``version_payload`` compares
  the installed ``versionCode`` with the published one, so "there is a newer
  build" cannot be argued with a version string.
"""

import hashlib
import secrets

from django.contrib.auth import authenticate
from django.contrib.auth.models import Group, User
from django.db import transaction
from django.utils import timezone

from . import audit
from .models import (
    AppRelease,
    AuditEvent,
    MobileProfile,
    MobileSession,
    PhoneChangeRequest,
)
from .phones import canonical_phone, display_phone, is_valid_phone

#: Shortest password the app accounts accept. The web form uses the same number
#: (``pages.MIN_PASSWORD_LENGTH``); a shorter one in one place than the other is
#: how a manager creates an account the other screen then refuses.
MIN_PASSWORD_LENGTH = 8

#: How long a token stays valid without being used. A warehouse phone that sits
#: in a drawer for a month should have to sign in again.
SESSION_MAX_AGE_DAYS = 30

#: A pending request older than this is ignored rather than blocking the user
#: forever (a manager who never looked).
REQUEST_MAX_AGE_DAYS = 14


class MobileError(Exception):
    """A refusal the app can show as-is."""

    def __init__(self, message, *, status=400, code=""):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def _hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _role_of(user):
    names = set(user.groups.values_list("name", flat=True))
    if "managers" in names:
        return "manager"
    if "shop_users" in names:
        return "shop_user"
    if "receive_mail" in names:
        return "receive_mail"
    return "user"


def profile_payload(user):
    profile = MobileProfile.for_user(user)
    pending = PhoneChangeRequest.pending_for(user)
    return {
        "username": user.get_username(),
        "displayName": (user.get_full_name() or user.get_username()),
        "role": _role_of(user),
        # Read-only in the app, on purpose: see the module docstring.
        "phone": display_phone(profile.phone) if profile else "",
        "phoneLocked": True,
        "mobileOnly": bool(profile and profile.mobile_only),
        "pendingPhoneChange": (
            {
                "requestedPhone": display_phone(pending.requested_phone),
                "createdAt": pending.created_at.isoformat(),
            }
            if pending
            else None
        ),
    }


def resolve_user(identifier):
    """The account behind what the user typed: a phone number OR a username.

    Both are accepted because both are how people know themselves: a warehouse
    manager reads the number off the users page, while an office user knows the
    user name they use on the web. The PHONE stays the app's identity either
    way — it is what the manager sets and what the app displays — so signing in
    with a user name does not give the app a second identity to keep in step.
    """
    text = str(identifier or "").strip()
    if not text:
        return None
    canonical = canonical_phone(text)
    if canonical and is_valid_phone(canonical):
        profile = (
            MobileProfile.objects.select_related("user").filter(phone=canonical).first()
        )
        if profile is not None:
            return profile.user
        # A number that belongs to nobody falls through to the user name, so a
        # numeric user name still works.
    return User.objects.filter(username__iexact=text).first()


def login(identifier, password, device="", request=None):
    """Sign in with a phone number or a user name, and the account's password.

    Neither the phone nor the user name is a credential — the phone is printed
    on every order, and a user name is guessable. The password is what proves
    it.
    """
    if not str(identifier or "").strip():
        raise MobileError(
            "أدخل رقم الهاتف أو اسم المستخدم.", status=400, code="phone_required"
        )

    user = resolve_user(identifier)
    if user is None:
        raise MobileError(
            "هذا الرقم أو اسم المستخدم غير مسجَّل في النظام. راجع مدير المخزن.",
            status=401,
            code="phone_unknown",
        )
    if not user.is_active:
        raise MobileError(
            "هذا الحساب موقوف. راجع مدير المخزن.", status=403, code="account_disabled"
        )

    # The request is required by django-axes (it is the project's auth backend
    # and counts failures per account and address). Passing it means an app
    # attacker hits the same lockout as the web form.
    # ``app_sign_in`` tells the one password backend which door this is: an
    # account created for the phone only is refused by the web form and admitted
    # here, and the refusal has to be decided with the credential, not globally.
    user = authenticate(
        request=request,
        username=user.get_username(),
        password=str(password or ""),
        app_sign_in=True,
    )
    if user is None or not user.is_active:
        raise MobileError(
            "كلمة المرور غير صحيحة.", status=401, code="bad_password"
        )

    # django writes last_login from login(); this path does not call it, so
    # without this the users page shows "—" for someone who signs in daily.
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])

    token = secrets.token_urlsafe(32)
    MobileSession.objects.create(
        user=user, token_hash=_hash(token), device=str(device or "")[:120]
    )
    audit.record(
        user=user,
        action=AuditEvent.LOGIN,
        entity="mobile_session",
        entity_id="",
        description=f"تطبيق الأندرويد · {device or 'جهاز غير معروف'}",
    )
    return {"token": token, "user": profile_payload(user)}


def session_for_token(token):
    """The session behind a bearer token, or None. Expired tokens are dropped."""
    if not token:
        return None
    session = (
        MobileSession.objects.select_related("user")
        .filter(token_hash=_hash(token), revoked_at__isnull=True)
        .first()
    )
    if session is None:
        return None
    if (timezone.now() - session.last_used_at).days >= SESSION_MAX_AGE_DAYS:
        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at"])
        return None
    if not session.user.is_active:
        return None
    MobileSession.objects.filter(pk=session.pk).update(last_used_at=timezone.now())
    return session


def logout(session):
    session.revoked_at = timezone.now()
    session.save(update_fields=["revoked_at"])
    audit.record(
        user=session.user,
        action=AuditEvent.LOGOUT,
        entity="mobile_session",
        entity_id=str(session.pk),
        description="تطبيق الأندرويد",
    )


def version_payload(installed_code=None):
    """What the app needs to decide whether to offer (or force) an update."""
    release = AppRelease.latest()
    if release is None:
        return {"updateAvailable": False, "latest": None}

    latest = {
        "versionName": release.version,
        "versionCode": release.version_code,
        "downloadUrl": release.download_url,
        "notes": release.notes,
        "mandatory": bool(release.mandatory),
        "sha256": release.sha256 or "",
        "sizeBytes": release.size_bytes,
        "publishedAt": release.created_at.isoformat(),
    }
    code = installed_code if isinstance(installed_code, int) else None
    # A release published before version_code existed cannot be compared; the
    # app then simply has nothing to offer rather than a guess.
    update = bool(code is not None and release.version_code and release.version_code > code)
    latest["updateAvailable"] = update
    latest["current"] = bool(code is not None and release.version_code == code)
    return {"updateAvailable": update, "latest": latest, "installedVersionCode": code}


# --------------------------------------------------------------------------
# The phone: one writer, and the request that leads to it
# --------------------------------------------------------------------------


APP_GROUP = "shop_users"

#: The name a phone-only account is given when nobody types one: the app signs
#: in by phone, so the user name is bookkeeping — but it must be unique and it
#: must be readable in the accounts table.
def _username_for_phone(phone):
    base = f"app-{phone}"
    candidate, n = base, 1
    while User.objects.filter(username__iexact=candidate).exists():
        n += 1
        candidate = f"{base}-{n}"
    return candidate


@transaction.atomic
def create_app_user(*, phone, password, name="", username="", actor=None):
    """A warehouse worker who signs in from the phone and nowhere else.

    One function, because an app account is three rows that must agree: the
    user, its group, and the phone that IS its identity. A form that wrote them
    separately would leave accounts that cannot sign in, or can sign in on the
    web by accident.
    """
    canonical = canonical_phone(phone)
    if not is_valid_phone(canonical):
        raise MobileError("رقم الهاتف غير صحيح.", code="phone_invalid")
    if MobileProfile.objects.filter(phone=canonical).exists():
        raise MobileError(
            "هذا الرقم مسجَّل بالفعل لحساب آخر.", status=409, code="phone_taken"
        )
    password = str(password or "")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise MobileError(
            f"كلمة المرور يجب أن تكون {MIN_PASSWORD_LENGTH} أحرف على الأقل.",
            code="password_too_short",
        )

    name = (name or "").strip()[:150]
    first, _, last = name.partition(" ")
    wanted = (username or "").strip()[:150] or _username_for_phone(canonical)
    if User.objects.filter(username__iexact=wanted).exists():
        raise MobileError(
            "اسم المستخدم مستخدم بالفعل.", status=409, code="username_taken"
        )

    user = User.objects.create_user(
        username=wanted, password=password, first_name=first, last_name=last.strip()
    )
    user.groups.add(Group.objects.get_or_create(name=APP_GROUP)[0])
    MobileProfile.objects.create(user=user, phone=canonical, mobile_only=True)
    audit.record(
        user=actor or user,
        action=AuditEvent.USER_CREATED,
        entity="user",
        entity_id=user.pk,
        description=f"{user.get_username()} · تطبيق · {display_phone(canonical)}",
    )
    return user


@transaction.atomic
def set_mobile_only(user, value, *, actor=None):
    """Mark an account as the phone's alone, or give it the web back."""
    profile = MobileProfile.for_user(user)
    if profile is None:
        raise MobileError(
            "هذا الحساب بلا رقم هاتف، فلا يمكن ربطه بالتطبيق.",
            code="no_phone",
        )
    profile.mobile_only = bool(value)
    profile.save(update_fields=["mobile_only", "updated_at"])
    audit.record(
        user=actor or user,
        action=AuditEvent.USER_UPDATED,
        entity="user",
        entity_id=user.pk,
        description=f"{user.get_username()} · "
        + ("تطبيق فقط" if value else "ويب وتطبيق"),
    )
    return profile


@transaction.atomic
def set_phone(user, phone, *, actor=None, note=""):
    """The ONLY function that writes a phone. Managers call it; the app cannot."""
    if not is_valid_phone(phone):
        raise MobileError("رقم الهاتف غير صحيح.", code="phone_invalid")
    canonical = canonical_phone(phone)

    other = MobileProfile.objects.filter(phone=canonical).exclude(user=user).first()
    if other is not None:
        raise MobileError(
            f"هذا الرقم مسجَّل بالفعل لـ {other.user.get_username()}.",
            status=409,
            code="phone_taken",
        )

    profile = MobileProfile.for_user(user)
    previous = profile.phone if profile else ""
    if profile is None:
        profile = MobileProfile.objects.create(user=user, phone=canonical)
    else:
        if previous == canonical:
            return profile
        profile.phone = canonical
        profile.save(update_fields=["phone", "updated_at"])

    audit.record(
        user=actor,
        action=AuditEvent.PHONE_CHANGED,
        entity="user",
        entity_id=str(user.pk),
        description=(
            f"{user.get_username()}: {display_phone(previous) or '—'} → "
            f"{display_phone(canonical)}"
            + (f" · {note}" if note else "")
        ),
    )
    return profile


def request_phone_change(user, requested_phone, reason=""):
    """A user asks; nothing changes until a manager decides."""
    if not is_valid_phone(requested_phone):
        raise MobileError("رقم الهاتف الجديد غير صحيح.", code="phone_invalid")
    canonical = canonical_phone(requested_phone)
    profile = MobileProfile.for_user(user)
    if profile and profile.phone == canonical:
        raise MobileError(
            "هذا هو رقمك الحالي بالفعل.", status=400, code="phone_unchanged"
        )
    if MobileProfile.objects.filter(phone=canonical).exclude(user=user).exists():
        raise MobileError(
            "هذا الرقم مسجَّل لحساب آخر. راجع مدير المخزن.", status=409, code="phone_taken"
        )

    pending = PhoneChangeRequest.pending_for(user)
    if pending is not None:
        # Re-submitting replaces the previous ask instead of piling up rows a
        # manager would have to read twice.
        pending.requested_phone = canonical
        pending.reason = str(reason or "")[:2000]
        pending.save(update_fields=["requested_phone", "reason"])
        request = pending
    else:
        request = PhoneChangeRequest.objects.create(
            user=user,
            current_phone=profile.phone if profile else "",
            requested_phone=canonical,
            reason=str(reason or "")[:2000],
        )

    audit.record(
        user=user,
        action=AuditEvent.PHONE_REQUESTED,
        entity="phone_change_request",
        entity_id=str(request.pk),
        description=f"{user.get_username()} → {display_phone(canonical)}",
    )
    return request


def decide_phone_change(request, manager, *, approve, note=""):
    """A manager's decision. Approval is the only way the phone moves."""
    if request.status != PhoneChangeRequest.PENDING:
        raise MobileError("هذا الطلب تم البتّ فيه بالفعل.", status=409, code="already_decided")

    if approve:
        set_phone(
            request.user,
            request.requested_phone,
            actor=manager,
            note=f"طلب #{request.pk}",
        )
        request.status = PhoneChangeRequest.APPROVED
    else:
        request.status = PhoneChangeRequest.REJECTED

    request.decided_by = manager
    request.decided_at = timezone.now()
    request.decision_note = str(note or "")[:2000]
    request.save(
        update_fields=["status", "decided_by", "decided_at", "decision_note"]
    )
    audit.record(
        user=manager,
        action=AuditEvent.PHONE_REQUEST_DECIDED,
        entity="phone_change_request",
        entity_id=str(request.pk),
        description=(
            f"{request.user.get_username()} → {display_phone(request.requested_phone)}"
            f" · {'موافقة' if approve else 'رفض'}"
        ),
    )
    return request
