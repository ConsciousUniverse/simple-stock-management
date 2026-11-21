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

from . import audit
from .models import AppRelease, AuditEvent, Item
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


def _redirect_users():
    from django.shortcuts import redirect

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
        User.objects.prefetch_related("groups").order_by("-is_active", "username")
    )
    for account in users:
        # The reader knows "warehouse manager", not the group's internal name.
        account.role_names = [role_label(group.name) for group in account.groups.all()]
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
        },
    )


def _selected_groups(request):
    names = request.POST.getlist("groups")
    return list(Group.objects.filter(name__in=names))


def _save_user(request):
    action = request.POST.get("action", "create")
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
        return _redirect_users()

    if action == "update":
        user = User.objects.filter(pk=request.POST.get("user_id")).first()
        if user is None:
            messages.error(request, _("That user does not exist."))
            return _redirect_users()
        was_active = user.is_active
        user.first_name = (request.POST.get("first_name") or "").strip()[:150]
        user.last_name = (request.POST.get("last_name") or "").strip()[:150]
        user.email = (request.POST.get("email") or "").strip()[:254]
        user.is_active = request.POST.get("is_active") == "on"
        user.save(update_fields=["first_name", "last_name", "email", "is_active"])
        user.groups.set(_selected_groups(request))
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
        return _redirect_users()

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
    return _redirect_users()


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
        if not version:
            messages.error(request, _("Enter the version."))
        elif AppRelease.objects.filter(version__iexact=version).exists():
            messages.error(request, _("That version is already published."))
        elif not _is_acceptable_download_url(download_url):
            messages.error(
                request,
                _("The download address must start with https:// or with /."),
            )
        else:
            release = AppRelease.objects.create(
                version=version,
                download_url=download_url,
                notes=notes,
                is_current=True,
                created_by=request.user,
            )
            audit.record(
                user=request.user,
                action=AuditEvent.RELEASE_PUBLISHED,
                entity="app_release",
                entity_id=release.pk,
                description=f"{release.version} · {release.download_url}",
            )
            messages.success(request, _("The build was published."))
        return _redirect_android()

    return render(
        request,
        "pages/android.html",
        {
            "latest": AppRelease.latest(),
            "releases": AppRelease.objects.select_related("created_by")[:20],
            "api_root": request.build_absolute_uri("/") + "api/",
        },
    )


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
