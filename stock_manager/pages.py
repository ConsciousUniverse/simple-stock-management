"""Standalone pages that are not a stock movement: users, the Android app, the
audit log, and the label picker.

They live apart from ``views.py`` because they are administration screens: each
one is a manager's tool (except the Android page, which every user may open),
and none of them moves stock.
"""

import re
from urllib.parse import urlparse

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.contrib.auth.views import PasswordChangeView
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from django.views.decorators.csrf import ensure_csrf_cookie

from . import audit, lockout, mobile
from .models import AppRelease, AuditEvent, Item, PhoneChangeRequest
from .phones import display_phone
from .permissions import is_warehouse_manager

AUDIT_PAGE_SIZE = 40
MIN_PASSWORD_LENGTH = 8

#: The three groups the app is built around, in the words the reader knows.
#: A group added later still shows under its own name rather than disappearing.
#: Lazy, because the label is resolved per request: a module-level ``_()`` call
#: would freeze whichever language happened to be active at import time.
ROLE_LABELS = {
    "managers": _lazy("Warehouse manager"),
    "shop_users": _lazy("Site user"),
    "receive_mail": _lazy("Mail receiver"),
}


def role_label(name):
    return ROLE_LABELS.get(name, name)


def _home():
    from django.shortcuts import redirect

    return redirect("/")


def _redirect_users(request=None):
    """Back to the account list, or to the page the form was opened from.

    The Android page carries the same account actions, and a manager working
    there must not be bounced to a different screen after saving. Only a local
    path is honoured, so a crafted form cannot walk the manager off the site.
    """
    from django.shortcuts import redirect

    target = (request.POST.get("next") if request is not None else "") or ""
    if target.startswith("/") and not target.startswith("//"):
        return redirect(target)
    return redirect("/users/")


def _manager_only(request):
    """The message a non-manager sees, or None when the user may continue."""
    if is_warehouse_manager(request.user):
        return None
    messages.error(request, _("Only a warehouse manager can open this page."))
    return True


@ensure_csrf_cookie
@login_required
def users_page(request):
    """The people who may sign in: their role, and whether they still may."""
    if _manager_only(request):
        return _home()

    if request.method == "POST":
        return _save_user(request)

    users = list(
        User.objects.prefetch_related("groups", "mobile_profile").order_by(
            "-is_active", "username"
        )
    )
    lock_states = lockout.states([account.get_username() for account in users])
    for account in users:
        # The reader knows "warehouse manager", not the group's internal name.
        account.role_names = [role_label(group.name) for group in account.groups.all()]
        account.is_app_only = bool(
            getattr(account, "mobile_profile", None)
            and account.mobile_profile.mobile_only
        )
        # A correct password can still be refused while a lockout is running.
        # That is not an error in the account, and the page has to say so.
        account.lock = lock_states[account.get_username()]
    editing = None
    raw_edit = (request.GET.get("edit") or "").strip()
    if raw_edit.isdigit():
        editing = User.objects.filter(pk=raw_edit).first()
    return render(
        request,
        "pages/users.html",
        {
            "users": users,
            "groups": [
                {"id": group.pk, "name": group.name, "label": role_label(group.name)}
                for group in Group.objects.order_by("name")
            ],
            "editing": editing,
            "editing_group_ids": set(editing.groups.values_list("id", flat=True))
            if editing
            else set(),
            "min_password_length": MIN_PASSWORD_LENGTH,
            "phone_requests": PhoneChangeRequest.objects.filter(
                status=PhoneChangeRequest.PENDING
            ).select_related("user"),
        },
    )


def _save_phone(request, action):
    """The phone an account signs in with — the app cannot touch it."""
    if action == "phone":
        user = User.objects.filter(pk=request.POST.get("user_id")).first()
        if user is None:
            messages.error(request, _("That user does not exist."))
            return _redirect_users(request)
        try:
            profile = mobile.set_phone(
                user,
                request.POST.get("phone") or "",
                actor=request.user,
                note=_("changed from the users page"),
            )
        except mobile.MobileError as exc:
            messages.error(request, exc.message)
            return _redirect_users(request)
        messages.success(
            request,
            _("The phone of %(name)s is now %(phone)s.")
            % {"name": user.get_username(), "phone": display_phone(profile.phone)},
        )
        return _redirect_users(request)

    record = PhoneChangeRequest.objects.filter(
        pk=request.POST.get("request_id"), status=PhoneChangeRequest.PENDING
    ).first()
    if record is None:
        messages.error(request, _("That request is no longer pending."))
        return _redirect_users(request)
    approve = request.POST.get("decision") == "approve"
    try:
        mobile.decide_phone_change(
            record,
            request.user,
            approve=approve,
            note=(request.POST.get("note") or "").strip(),
        )
    except mobile.MobileError as exc:
        messages.error(request, exc.message)
        return _redirect_users(request)
    messages.success(
        request,
        _("The phone of %(name)s was changed to %(phone)s.")
        % {
            "name": record.user.get_username(),
            "phone": display_phone(record.requested_phone),
        }
        if approve
        else _("The request of %(name)s was refused.")
        % {"name": record.user.get_username()},
    )
    return _redirect_users(request)


def _create_app_user(request):
    """An account that signs in from the phone, with its number in one step.

    Creating the user and then hunting for their row to set a phone leaves
    accounts that exist and cannot sign in; the phone IS the identity, so it is
    required here.
    """
    try:
        user = mobile.create_app_user(
            phone=request.POST.get("phone") or "",
            password=request.POST.get("password") or "",
            name=request.POST.get("name") or "",
            username=request.POST.get("username") or "",
            actor=request.user,
        )
    except mobile.MobileError as exc:
        messages.error(request, exc.message)
        return _redirect_users(request)
    messages.success(
        request,
        _("The app account %(name)s was created. They sign in with the phone number.")
        % {"name": user.get_username()},
    )
    return _redirect_users(request)


def _unlock_user(request):
    """Clear a lockout. The lockout page tells the person to ask for exactly this."""
    raw_id = (request.POST.get("user_id") or "").strip()
    user = User.objects.filter(pk=raw_id).first() if raw_id.isdigit() else None
    if user is None:
        messages.error(request, _("That user does not exist."))
        return _redirect_users(request)
    removed = lockout.clear(user.get_username())
    audit.record(
        user=request.user,
        action=AuditEvent.USER_UNLOCKED,
        entity="user",
        entity_id=user.pk,
        description=f"{user.get_username()} · {removed} failed attempts cleared",
    )
    messages.success(
        request,
        _("The sign-in lockout of %(name)s was cleared. They can sign in now.")
        % {"name": user.get_username()},
    )
    return _redirect_users(request)


def _clear_device(request):
    """Free an app account from the phone it is bound to.

    The one action that lets a person move to a new phone: until this is done,
    the second phone is refused by name. Clearing also revokes the tokens the
    old phone is holding, so a phone that was lost stops working now rather
    than when its token expires.
    """
    from stock_manager import mobile

    raw_id = (request.POST.get("user_id") or "").strip()
    user = User.objects.filter(pk=raw_id).first() if raw_id.isdigit() else None
    if user is None:
        messages.error(request, _("That user does not exist."))
        return _redirect_users(request)
    had_device = mobile.clear_device(user, by=request.user)
    if had_device:
        messages.success(
            request,
            _(
                "The device was cleared from %(name)s. They can sign in on a new phone now."
            )
            % {"name": user.get_username()},
        )
    else:
        messages.info(
            request,
            _("%(name)s was not bound to any phone.") % {"name": user.get_username()},
        )
    return _redirect_users(request)


def _toggle_active(request):
    """Close or reopen an account without opening the edit panel."""
    raw_id = (request.POST.get("user_id") or "").strip()
    user = User.objects.filter(pk=raw_id).first() if raw_id.isdigit() else None
    if user is None:
        messages.error(request, _("That user does not exist."))
        return _redirect_users(request)
    if user.pk == request.user.pk:
        messages.error(request, _("You cannot close your own account."))
        return _redirect_users(request)
    # Closing the last manager would leave nobody able to reopen anyone, and
    # there is no shell on the deployed host to undo it.
    if user.is_active and _is_last_manager(user):
        messages.error(request, _("This is the last warehouse manager."))
        return _redirect_users(request)
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    audit.record(
        user=request.user,
        action=(
            AuditEvent.USER_UPDATED if user.is_active else AuditEvent.USER_DEACTIVATED
        ),
        entity="user",
        entity_id=user.pk,
        description=f"{user.get_username()} · "
        + ("reopened" if user.is_active else "closed"),
    )
    messages.success(
        request,
        (
            _("The account of %(name)s was reopened.")
            if user.is_active
            else _("The account of %(name)s was closed.")
        )
        % {"name": user.get_username()},
    )
    return _redirect_users(request)


def _is_last_manager(user):
    """True when this account is the only active warehouse manager left."""
    if not user.groups.filter(name="managers").exists():
        return False
    return not (
        User.objects.filter(groups__name="managers", is_active=True)
        .exclude(pk=user.pk)
        .exists()
    )


def _selected_groups(request):
    names = request.POST.getlist("groups")
    return list(Group.objects.filter(name__in=names))


def _save_user(request):
    action = request.POST.get("action", "create")

    if action in {"phone", "phone-request"}:
        return _save_phone(request, action)
    if action == "app-user":
        return _create_app_user(request)
    if action == "toggle-active":
        return _toggle_active(request)
    if action == "unlock":
        return _unlock_user(request)
    if action == "clear-device":
        return _clear_device(request)
    if action == "password":
        user = User.objects.filter(pk=request.POST.get("user_id")).first()
        password = request.POST.get("password") or ""
        if user is None:
            messages.error(request, _("That user does not exist."))
        elif len(password) < MIN_PASSWORD_LENGTH:
            messages.error(
                request,
                _("The password must be at least %(n)s characters.")
                % {"n": MIN_PASSWORD_LENGTH},
            )
        else:
            user.set_password(password)
            user.save(update_fields=["password"])
            audit.record(
                user=request.user,
                action=AuditEvent.PASSWORD_CHANGED,
                entity="user",
                entity_id=user.pk,
                description=f"{user.get_username()} (by {request.user.get_username()})",
            )
            messages.success(request, _("The password was changed."))
        return _redirect_users(request)

    if action == "update":
        user = User.objects.filter(pk=request.POST.get("user_id")).first()
        if user is None:
            messages.error(request, _("That user does not exist."))
            return _redirect_users(request)
        was_active = user.is_active
        user.first_name = (request.POST.get("first_name") or "").strip()[:150]
        user.last_name = (request.POST.get("last_name") or "").strip()[:150]
        user.email = (request.POST.get("email") or "").strip()[:254]
        user.is_active = request.POST.get("is_active") == "on"
        user.save(update_fields=["first_name", "last_name", "email", "is_active"])
        user.groups.set(_selected_groups(request))
        # Only an account with a phone can be app-only; without one the box is
        # meaningless, and flipping it would lock a web user out for nothing.
        if request.POST.get("has_phone") == "1":
            try:
                mobile.set_mobile_only(
                    user, request.POST.get("mobile_only") == "on", actor=request.user
                )
            except mobile.MobileError as exc:
                messages.error(request, exc.message)
        audit.record(
            user=request.user,
            action=(
                AuditEvent.USER_DEACTIVATED
                if was_active and not user.is_active
                else AuditEvent.USER_UPDATED
            ),
            entity="user",
            entity_id=user.pk,
            description=f"{user.get_username()} · "
            + (", ".join(g.name for g in user.groups.all()) or "—"),
        )
        messages.success(request, _("The user was saved."))
        return _redirect_users(request)

    # create
    username = (request.POST.get("username") or "").strip()
    password = request.POST.get("password") or ""
    if not username:
        messages.error(request, _("Enter a user name."))
    elif User.objects.filter(username__iexact=username).exists():
        messages.error(request, _("That user name is already taken."))
    elif len(password) < MIN_PASSWORD_LENGTH:
        messages.error(
            request,
            _("The password must be at least %(n)s characters.")
            % {"n": MIN_PASSWORD_LENGTH},
        )
    else:
        user = User.objects.create_user(
            username=username,
            password=password,
            email=(request.POST.get("email") or "").strip(),
            first_name=(request.POST.get("first_name") or "").strip(),
            last_name=(request.POST.get("last_name") or "").strip(),
        )
        user.groups.set(_selected_groups(request))
        audit.record(
            user=request.user,
            action=AuditEvent.USER_CREATED,
            entity="user",
            entity_id=user.pk,
            description=f"{user.get_username()} · "
            + (", ".join(g.name for g in user.groups.all()) or "—"),
        )
        messages.success(request, _("The user was created."))
    return _redirect_users(request)


def _is_acceptable_download_url(value: str) -> bool:
    """An address a phone can open: https, or a path on this same site.

    Anything else (``javascript:``, a bare host, a relative path that would
    resolve somewhere unexpected) is refused rather than published: the link is
    handed to every user as "download the app".
    """
    if not value:
        return False
    parsed = urlparse(value)
    if parsed.scheme in ("http", "https"):
        return bool(parsed.netloc)
    if value.startswith("/"):
        return url_has_allowed_host_and_scheme(value, allowed_hosts=None)
    return False


@ensure_csrf_cookie
@login_required
def android_page(request):
    """The Android app: the current build, its history, and where to get it."""
    if request.method == "POST":
        if not is_warehouse_manager(request.user):
            messages.error(request, _("Only a warehouse manager can publish a build."))
            return _redirect_android()

        version = (request.POST.get("version") or "").strip()[:40]
        download_url = (request.POST.get("download_url") or "").strip()[:500]
        notes = (request.POST.get("notes") or "").strip()
        raw_code = (request.POST.get("version_code") or "").strip()
        sha256 = (request.POST.get("sha256") or "").strip().lower()[:64]
        raw_size = (request.POST.get("size_bytes") or "").strip()
        mandatory = request.POST.get("mandatory") == "on"
        latest = AppRelease.latest()
        version_code = int(raw_code) if raw_code.isdigit() else None

        if not version:
            messages.error(request, _("Enter the version."))
        elif AppRelease.objects.filter(version__iexact=version).exists():
            messages.error(request, _("That version is already published."))
        elif not raw_code.isdigit():
            # The app compares this number with its own; a release without one
            # would never be offered as an update.
            messages.error(
                request, _("Enter the build number (a whole number that only grows).")
            )
        elif latest and latest.version_code and version_code <= latest.version_code:
            messages.error(
                request,
                _(
                    "The build number must be higher than %(code)s, or the phones on that build would not see the update."
                )
                % {"code": latest.version_code},
            )
        elif sha256 and (len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256)):
            messages.error(request, _("The checksum must be 64 hexadecimal characters."))
        elif not _is_acceptable_download_url(download_url):
            messages.error(
                request,
                _("The download address must start with https:// or with /."),
            )
        else:
            release = AppRelease.objects.create(
                version=version,
                version_code=version_code,
                download_url=download_url,
                notes=notes,
                sha256=sha256,
                size_bytes=int(raw_size) if raw_size.isdigit() else None,
                mandatory=mandatory,
                is_current=True,
                created_by=request.user,
            )
            audit.record(
                user=request.user,
                action=AuditEvent.RELEASE_PUBLISHED,
                entity="app_release",
                entity_id=release.pk,
                description=(
                    f"{release.version} (build {release.version_code}) · "
                    f"{release.download_url}"
                    + (" · إلزامي" if release.mandatory else "")
                ),
            )
            messages.success(request, _("The build was published."))
        return _redirect_android()

    from stock_manager import releases

    published = releases.latest_release()
    # The people who sign in from the phone: an account is usable there once it
    # has a phone number, so that is the list this page is responsible for.
    app_users = list(
        User.objects.filter(mobile_profile__isnull=False)
        .select_related("mobile_profile")
        .prefetch_related("groups")
        .order_by("-is_active", "username")
    )
    lock_states = lockout.states([account.get_username() for account in app_users])
    for account in app_users:
        account.role_names = [role_label(group.name) for group in account.groups.all()]
        account.is_app_only = bool(
            getattr(account, "mobile_profile", None)
            and account.mobile_profile.mobile_only
        )
        account.lock = lock_states[account.get_username()]
        account.phone_display = display_phone(account.mobile_profile.phone)
        account.device_label = account.mobile_profile.device_label
        account.device_bound_at = account.mobile_profile.device_bound_at
    return render(
        request,
        "pages/android.html",
        {
            "app_users": app_users,
            "app_user_count": len(app_users),
            "app_user_active": sum(1 for account in app_users if account.is_active),
            "min_password_length": MIN_PASSWORD_LENGTH,
            # What the phones are offered, and where it came from: the page must
            # not show a build the app is not told about, or the reverse.
            "latest": releases.as_row(releases.select_release()),
            "auto": releases.as_row(published),
            # One date for the tile: whichever build the phones are offered.
            "published_on": _published_on(
                releases.as_row(published) or releases.as_row(releases.select_release())
            ),
            # The tile shows the version a person says out loud ("1.2.0"); the
            # release's own name ("Warehouse 1.2.0 (build 3)") wraps onto three
            # lines in a tile and pushes its neighbours out of line.
            "version_short": _version_short(
                releases.as_row(published) or releases.as_row(releases.select_release())
            ),
            "auto_failed": published is None,
            "auto_error": releases.last_error(),
            "release_repo": releases.RELEASES_REPO,
            "build_count": AppRelease.objects.count() + (1 if published else 0),
            "releases": AppRelease.objects.select_related("created_by")[:20],
            "api_root": request.build_absolute_uri("/") + "api/",
        },
    )


def _version_short(row):
    """The dotted version in a release name, or the name itself."""
    name = str(getattr(row, "versionName", None) or getattr(row, "version", "") or "")
    found = re.search(r"\d+(?:\.\d+)+", name)
    return found.group(0) if found else name


def _published_on(row):
    """The date part of a release row, or None when there is no build."""
    stamp = getattr(row, "published_at", None) or ""
    return stamp[:10] if stamp else None


def _redirect_android():
    from django.shortcuts import redirect

    return redirect("/android/")


def _parse_date(value):
    from datetime import date

    value = (value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@ensure_csrf_cookie
@login_required
def audit_page(request):
    """The trail: every recorded action, filtered by area, person and date."""
    if _manager_only(request):
        return _home()

    events = AuditEvent.objects.select_related("actor")
    area = (request.GET.get("area") or "").strip()
    actor = (request.GET.get("actor") or "").strip()
    query = (request.GET.get("q") or "").strip()
    date_from = _parse_date(request.GET.get("from"))
    date_to = _parse_date(request.GET.get("to"))

    if area:
        actions = [
            action
            for action, action_area in AuditEvent.ACTION_AREA.items()
            if action_area == area
        ]
        events = events.filter(action__in=actions)
    if actor:
        events = events.filter(
            Q(actor_name__icontains=actor) | Q(actor__username__icontains=actor)
        )
    if query:
        events = events.filter(
            Q(description__icontains=query) | Q(entity_id__icontains=query)
        )
    if date_from:
        events = events.filter(created_at__date__gte=date_from)
    if date_to:
        events = events.filter(created_at__date__lte=date_to)

    paginator = Paginator(events, AUDIT_PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    querystring = request.GET.copy()
    querystring.pop("page", None)

    return render(
        request,
        "pages/audit.html",
        {
            "page_obj": page,
            "events": page.object_list,
            "total": paginator.count,
            "areas": AuditEvent.AREA_CHOICES,
            "actions": AuditEvent.ACTION_CHOICES,
            "filters": {
                "area": area,
                "actor": actor,
                "q": query,
                "from": request.GET.get("from", ""),
                "to": request.GET.get("to", ""),
            },
            "querystring": querystring.urlencode(),
        },
    )


@ensure_csrf_cookie
@login_required
def labels_page(request):
    """Pick the items to label, then print the sheet.

    ``/labels/?skus=…`` renders the printable sheet (what the print button in the
    warehouse panel links to); without skus it is the picker, because an empty
    sheet answers nothing.
    """
    from .views import print_labels

    if (request.GET.get("skus") or "").strip():
        return print_labels(request)

    query = (request.GET.get("q") or "").strip()
    items = Item.objects.filter(is_active=True)
    if query:
        items = items.filter(Q(sku__icontains=query) | Q(description__icontains=query))
    return render(
        request,
        "pages/labels_picker.html",
        {
            "items": items.order_by("sku")[:300],
            "query": query,
            "print_url": "/labels/",
        },
    )


class AuditedPasswordChangeView(PasswordChangeView):
    """The portal's own password change, recorded in the audit trail."""

    def form_valid(self, form):
        response = super().form_valid(form)
        audit.record(
            user=self.request.user,
            action=AuditEvent.PASSWORD_CHANGED,
            entity="user",
            entity_id=self.request.user.pk,
            description=self.request.user.get_username(),
        )
        return response
