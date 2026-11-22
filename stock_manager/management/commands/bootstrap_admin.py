"""Create the initial administrator and the role groups on first deploy.

Idempotent: an existing user is never modified, so a redeploy cannot reset a
password that was changed in the UI. Without the ``DJANGO_SUPERUSER_*``
variables the command only makes sure the role groups exist.

It also runs ``reset_user`` when ``RESET_USER_*`` is set. That is the way back
in when the last manager is locked out or has forgotten the password — and it
hangs off THIS command on purpose: this is the one already in the deploy's
build command, so the owner only has to set two variables and redeploy.
"""

import os

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

ROLE_GROUPS = ("managers", "shop_users", "receive_mail")


class Command(BaseCommand):
    help = "Create the role groups and, when DJANGO_SUPERUSER_* is set, the first administrator."

    def handle(self, *args, **options):
        groups = {}
        for name in ROLE_GROUPS:
            groups[name], _ = Group.objects.get_or_create(name=name)

        username = os.getenv("DJANGO_SUPERUSER_USERNAME")
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD")
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", "")

        self._reset_when_asked()

        if not username or not password:
            self.stdout.write(
                "bootstrap_admin: DJANGO_SUPERUSER_* not set, only the role groups were ensured."
            )
            return

        user, created = User.objects.get_or_create(
            username=username, defaults={"email": email}
        )
        if created:
            user.set_password(password)
            user.is_staff = True
            user.is_superuser = True
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f"bootstrap_admin: created administrator '{username}'.")
            )
        else:
            self.stdout.write(
                f"bootstrap_admin: '{username}' already exists, left unchanged."
            )

        # The dashboard gates the warehouse controls on the 'managers' group,
        # not on is_superuser, so an administrator needs the membership too.
        user.groups.add(groups["managers"])

    @staticmethod
    def _reset_when_asked():
        """``RESET_USER_*`` is one implementation, shared with ``reset_user``."""
        if not (os.getenv("RESET_USER_USERNAME") and os.getenv("RESET_USER_PASSWORD")):
            return
        from django.core.management import call_command

        call_command("reset_user")
