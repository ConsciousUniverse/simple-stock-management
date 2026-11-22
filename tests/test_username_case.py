"""A username is typed from memory — the capitals are not part of the secret.

``Lifeendy`` was the account and ``lifeendy`` was what got typed: Django matches
usernames exactly, so the account was never found, every attempt failed, and
each one was counted against a name no account has. The person ended up locked
out of an account they never reached.
"""

import pytest
from django.contrib.auth.models import User

from stock_manager.auth import axes_username, canonical_username

pytestmark = pytest.mark.django_db

PASSWORD = "test-pass-123"


def _user(username="Lifeendy"):
    return User.objects.create_user(username=username, password=PASSWORD)


def test_the_other_spelling_finds_the_account():
    from django.contrib.auth import authenticate

    user = _user()

    assert authenticate(username="lifeendy", password=PASSWORD) == user
    assert authenticate(username="LIFEENDY", password=PASSWORD) == user
    assert authenticate(username="Lifeendy", password=PASSWORD) == user


def test_a_wrong_password_is_still_refused():
    from django.contrib.auth import authenticate

    _user()

    assert authenticate(username="lifeendy", password="nope") is None


def test_the_other_spelling_does_not_become_a_way_around_the_password():
    from django.contrib.auth import authenticate

    _user()

    assert authenticate(username="lifeendy", password="") is None


def test_two_accounts_differing_only_in_case_are_never_confused():
    from django.contrib.auth import authenticate

    lower = User.objects.create_user(username="clerk", password=PASSWORD)
    User.objects.create_user(username="CLERK", password="another-pass-123")

    # The exact spelling always wins, so each account keeps its own password.
    assert authenticate(username="clerk", password=PASSWORD) == lower
    assert authenticate(username="CLERK", password="another-pass-123") is not None
    assert authenticate(username="Clerk", password=PASSWORD) is None


def test_the_lockout_counts_one_person_not_one_spelling():
    """``axes`` must key on the canonical name, or a lock follows the typo."""
    assert axes_username(None, {"username": "Lifeendy"}) == "lifeendy"
    assert axes_username(None, {"username": "  lifeendy "}) == "lifeendy"
    assert axes_username(None, {}) == ""


def test_the_web_form_accepts_the_lowercase_spelling(client):
    _user()

    response = client.post(
        "/accounts/login/", {"username": "lifeendy", "password": PASSWORD}, follow=True
    )

    assert response.wsgi_request.user.is_authenticated
    assert response.wsgi_request.user.username == "Lifeendy"


def test_canonical_username_is_the_one_rule():
    assert canonical_username("  LiFeEnDy ") == "lifeendy"
    assert canonical_username(None) == ""
