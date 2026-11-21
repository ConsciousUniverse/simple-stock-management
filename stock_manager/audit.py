"""The audit trail: who did what, and when.

Events are written by the WRITE paths and by Django's auth signals, never by a
read path — a log of page views is not an audit log. Writing is best-effort:
the action has already happened by then, so failing to describe it must never
fail the action itself (a loud log line is the fallback).

The acting user is taken from the request through :class:`CurrentActorMiddleware`
so a write path deep inside a service function can still be attributed without
threading the request through every signature.
"""

import logging
import threading

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from .models import AuditEvent

logger = logging.getLogger("stock_manager.audit")

_state = threading.local()


def set_current_actor(user):
    _state.user = user if getattr(user, "is_authenticated", False) else None


def clear_current_actor():
    _state.user = None


def current_actor():
    return getattr(_state, "user", None)


def record(user=None, action=None, entity="", entity_id="", description=""):
    """Describe one action. Never raises: the caller's work is already done."""
    if action is None:
        raise ValueError("record() needs an action")
    actor = user if user is not None else current_actor()
    if actor is not None and not getattr(actor, "is_authenticated", True):
        actor = None
    try:
        AuditEvent.objects.create(
            actor=actor,
            actor_name=(getattr(actor, "username", "") or "")[:150],
            action=action,
            entity=(entity or "")[:40],
            entity_id=str(entity_id or "")[:80],
            description=description or "",
        )
    except Exception:  # pragma: no cover - depends on a failing database
        logger.exception("Could not write the audit event %r", action)


class CurrentActorMiddleware:
    """Remembers who is acting for the duration of one request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_actor(getattr(request, "user", None))
        try:
            return self.get_response(request)
        finally:
            clear_current_actor()


class AuditedPasswordChangeView:
    """Mixin: a self-service password change belongs in the trail too."""

    @staticmethod
    def _record_password_change(request):
        record(
            user=request.user,
            action=AuditEvent.PASSWORD_CHANGED,
            entity="user",
            entity_id=request.user.pk,
            description=request.user.get_username(),
        )


@receiver(user_logged_in)
def _record_login(sender, request, user, **kwargs):
    record(
        user=user,
        action=AuditEvent.LOGIN,
        entity="user",
        entity_id=user.pk,
        # The actor column already names the account, so repeating it in the
        # details would be noise.
        description="",
    )


@receiver(user_logged_out)
def _record_logout(sender, request, user, **kwargs):
    if user is None:
        return
    record(
        user=user,
        action=AuditEvent.LOGOUT,
        entity="user",
        entity_id=user.pk,
        description="",
    )


@receiver(user_login_failed)
def _record_failed_login(sender, credentials, request=None, **kwargs):
    # The password is never touched: the trail records attempts, not secrets.
    username = str((credentials or {}).get("username") or "")[:150]
    record(
        action=AuditEvent.LOGIN_FAILED,
        entity="user",
        entity_id=username,
        description=username,
    )
