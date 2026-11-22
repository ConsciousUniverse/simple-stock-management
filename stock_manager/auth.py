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

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

#: Why the web form refused someone whose password was RIGHT. The sign-in page
#: shows these; a wrong password never produces one, so nothing is revealed to
#: anyone who does not already know the password.
REFUSAL_APP_ONLY = "app_only"
REFUSAL_INACTIVE = "inactive"


def _refuse(request, reason):
    if request is not None:
        request.login_refusal = reason


def canonical_username(username):
    """One spelling for one account: the lockout must not key on the capitals."""
    return (username or "").strip().lower()


def axes_username(request, credentials=None):
    """What ``axes`` counts against.

    Django matches usernames exactly, so ``lifeendy`` never found ``Lifeendy`` —
    every attempt failed AND was counted under a name no account has, so the
    person could be locked out of an account they were never reaching.
    """
    return canonical_username((credentials or {}).get("username"))


class WarehouseBackend(ModelBackend):
    """The project's password backend: one refusal, for the app-only accounts.

    A refusal is only *named* after the password checks out: telling an outsider
    which numbers have accounts is exactly what the generic message prevents.
    """

    def authenticate(self, request, username=None, password=None, app_sign_in=False, **kwargs):
        user = self._authenticate_case_insensitive(request, username, password, **kwargs)
        if user is not None:
            if app_sign_in:
                return user
            if self._is_app_only(user):
                # ``user_login_failed`` records the attempt; the reason travels
                # on the request so the trail carries it instead of a guess.
                _refuse(request, REFUSAL_APP_ONLY)
                return None
            return user

        # ``super()`` also refuses a CLOSED account, and a closed account is not
        # a wrong password. Check only after the password matches, so the answer
        # is given to the person who owns the account and to nobody else.
        candidate = self._find_user(username)
        if (
            candidate is not None
            and not candidate.is_active
            and candidate.check_password(password or "")
        ):
            _refuse(request, REFUSAL_INACTIVE)
        return None

    def _authenticate_case_insensitive(self, request, username, password, **kwargs):
        """Try the spelling given, then the account's own spelling.

        A username is typed from memory: ``Lifeendy`` and ``lifeendy`` are the
        same person. The exact spelling wins; the case-insensitive match is only
        used when it identifies ONE account, so two accounts that differ only in
        capitals can never be confused with each other.
        """
        user = super().authenticate(request, username, password, **kwargs)
        if user is not None:
            return user
        user_model = get_user_model()
        exact = self._find_user(username)
        if exact is not None:
            return None
        matches = list(
            user_model._default_manager.filter(username__iexact=(username or "").strip())[:2]
        )
        if len(matches) != 1:
            return None
        return super().authenticate(request, matches[0].get_username(), password, **kwargs)

    @staticmethod
    def _find_user(username):
        if not username:
            return None
        try:
            return get_user_model()._default_manager.get_by_natural_key(username)
        except get_user_model().DoesNotExist:
            return None

    @staticmethod
    def _is_app_only(user):
        profile = getattr(user, "mobile_profile", None)
        return bool(profile is not None and profile.mobile_only)


def is_app_only(user):
    """True when this account signs in from the phone and nowhere else."""
    return WarehouseBackend._is_app_only(user)
