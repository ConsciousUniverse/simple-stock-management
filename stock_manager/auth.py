"""Who may come in through which door.

There are two doors: the web sign-in form, and the phone app. A warehouse
worker may only have the phone, so an "app account" is refused by the web form
rather than admitted to pages it has no business in.

The refusal is the form's ordinary one, not "this account is app-only": saying
which numbers have accounts tells an outsider which numbers to attack. The
sign-in page carries a standing line instead — a worker's account signs in from
the phone app — so the person reading it knows where to go without the form
naming anybody.

The app's own sign-in passes ``app_sign_in=True`` through ``authenticate()``,
which is why one backend can answer for both doors without a global flag: the
flag travels with the credential check, not with the process.
"""

from django.contrib.auth.backends import ModelBackend


class WarehouseBackend(ModelBackend):
    """The project's password backend: one refusal, for the app-only accounts."""

    def authenticate(self, request, username=None, password=None, app_sign_in=False, **kwargs):
        user = super().authenticate(request, username, password, **kwargs)
        if user is None:
            return None
        if app_sign_in:
            return user
        if self._is_app_only(user):
            return None
        return user

    @staticmethod
    def _is_app_only(user):
        profile = getattr(user, "mobile_profile", None)
        return bool(profile is not None and profile.mobile_only)


def is_app_only(user):
    """True when this account signs in from the phone and nowhere else."""
    return WarehouseBackend._is_app_only(user)
