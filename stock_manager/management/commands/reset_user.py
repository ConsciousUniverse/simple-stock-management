"""Reset one account's password on deploy — the way back in when nobody can sign in.

Accounts are created by a manager from ``/users/``, which is exactly the door
that is shut when the last manager is locked out or has forgotten the password.
The deploy already runs as the service's owner, so it can carry the one
instruction the owner gives it:

    RESET_USER_USERNAME=manager
    RESET_USER_PASSWORD=<a new password>
    RESET_USER_GROUP=managers      # optional, defaults to managers
    RESET_USER_STAFF=True          # optional

Nothing happens unless BOTH variables are set, so an ordinary deploy never
touches an account. Anyone who can set these variables can already set
``DATABASE_URL`` or ``DJANGO_SECRET_KEY``, so this grants no new power — and the
reset is written to the audit trail, with the attempt counter cleared so the
account is not still locked when the new password is used.
"""

import os

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from ...audit import record
from ...models import AuditEvent


class Command(BaseCommand):
    help = "Reset one account's password from RESET_USER_* (and clear its lockout)."

    def handle(self, *args, **options):
        username = (os.getenv("RESET_USER_USERNAME") or "").strip()
        password = os.getenv("RESET_USER_PASSWORD") or ""
        if not username or not password:
            self.stdout.write(
                "reset_user: RESET_USER_* not set, no account was touched."
            )
            return

        group_name = (os.getenv("RESET_USER_GROUP") or "managers").strip()
        staff = (os.getenv("RESET_USER_STAFF") or "True").strip().lower() not in (
            "0",
            "false",
            "no",
        )

        user, created = User.objects.get_or_create(username=username)
        user.set_password(password)
        user.is_active = True
        if staff:
            user.is_staff = True
        user.save()

        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(group)

        cleared = self._clear_lockout(username)

        record(
            action=AuditEvent.USER_RESET,
            entity="user",
            entity_id=user.pk,
            description=f"{username} · password reset on deploy",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"reset_user: {'created' if created else 'reset'} '{username}' "
                f"in group '{group_name}', {cleared} lockout row(s) cleared."
            )
        )

    @staticmethod
    def _clear_lockout(username):
        """A reset password is useless while the username is still locked."""
        try:
            from axes.models import AccessAttempt
        except Exception:  # pragma: no cover - axes is a hard dependency
            return 0
        deleted, _ = AccessAttempt.objects.filter(username__iexact=username).delete()
        return deleted
