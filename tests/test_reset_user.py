"""The way back in when nobody can sign in.

Accounts are created from ``/users/``, which is the door that is shut when the
last manager is locked out or has forgotten the password. The deploy can carry
one instruction from the owner — and only when the owner sets BOTH variables.
"""

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from axes.models import AccessAttempt

from stock_manager.models import AuditEvent

pytestmark = pytest.mark.django_db


def _attempt(username, failures=3):
    return AccessAttempt.objects.create(
        user_agent="pytest",
        username=username,
        http_accept="",
        path_info="/accounts/login/",
        get_data="",
        post_data="",
        failures_since_start=failures,
    )


def test_nothing_is_touched_without_the_variables(monkeypatch):
    monkeypatch.delenv("RESET_USER_USERNAME", raising=False)
    monkeypatch.delenv("RESET_USER_PASSWORD", raising=False)

    call_command("reset_user")

    assert not User.objects.filter(username="manager").exists()


def test_both_variables_are_needed(monkeypatch):
    monkeypatch.setenv("RESET_USER_USERNAME", "manager")
    monkeypatch.delenv("RESET_USER_PASSWORD", raising=False)

    call_command("reset_user")

    assert not User.objects.filter(username="manager").exists()


def test_it_creates_the_account_in_the_managers_group(monkeypatch):
    monkeypatch.setenv("RESET_USER_USERNAME", "manager")
    monkeypatch.setenv("RESET_USER_PASSWORD", "new-pass-12345")

    call_command("reset_user")

    user = User.objects.get(username="manager")
    assert user.check_password("new-pass-12345")
    assert user.is_active and user.is_staff
    assert user.groups.filter(name="managers").exists()


def test_it_resets_an_existing_account_and_reopens_it(monkeypatch):
    user = User.objects.create_user(username="manager", password="old-pass-12345")
    user.is_active = False
    user.save(update_fields=["is_active"])
    monkeypatch.setenv("RESET_USER_USERNAME", "manager")
    monkeypatch.setenv("RESET_USER_PASSWORD", "new-pass-12345")

    call_command("reset_user")

    user.refresh_from_db()
    assert user.check_password("new-pass-12345")
    assert user.is_active is True


def test_a_reset_password_is_useless_while_the_account_is_locked(monkeypatch):
    User.objects.create_user(username="manager", password="old-pass-12345")
    _attempt("manager")
    monkeypatch.setenv("RESET_USER_USERNAME", "manager")
    monkeypatch.setenv("RESET_USER_PASSWORD", "new-pass-12345")

    call_command("reset_user")

    assert AccessAttempt.objects.filter(username="manager").count() == 0


def test_the_reset_is_audited(monkeypatch):
    monkeypatch.setenv("RESET_USER_USERNAME", "manager")
    monkeypatch.setenv("RESET_USER_PASSWORD", "new-pass-12345")

    call_command("reset_user")

    entry = AuditEvent.objects.filter(action=AuditEvent.USER_RESET).first()
    assert entry is not None
    assert "manager" in entry.description


def test_the_group_can_be_chosen(monkeypatch):
    Group.objects.create(name="shop_users")
    monkeypatch.setenv("RESET_USER_USERNAME", "clerk")
    monkeypatch.setenv("RESET_USER_PASSWORD", "new-pass-12345")
    monkeypatch.setenv("RESET_USER_GROUP", "shop_users")

    call_command("reset_user")

    assert User.objects.get(username="clerk").groups.filter(name="shop_users").exists()


def test_the_new_password_is_never_printed(monkeypatch, capsys):
    monkeypatch.setenv("RESET_USER_USERNAME", "manager")
    monkeypatch.setenv("RESET_USER_PASSWORD", "new-pass-12345")

    call_command("reset_user")

    out = capsys.readouterr().out
    assert "new-pass-12345" not in out
    assert "manager" in out


class TestTheDeployCarriesIt:
    """``bootstrap_admin`` is already in the build command; it runs the reset."""

    def test_bootstrap_resets_when_the_variables_are_set(self, monkeypatch):
        monkeypatch.setenv("RESET_USER_USERNAME", "manager")
        monkeypatch.setenv("RESET_USER_PASSWORD", "new-pass-12345")

        call_command("bootstrap_admin")

        user = User.objects.get(username="manager")
        assert user.check_password("new-pass-12345")
        assert user.groups.filter(name="managers").exists()

    def test_bootstrap_alone_still_touches_no_account(self, monkeypatch):
        monkeypatch.delenv("RESET_USER_USERNAME", raising=False)
        monkeypatch.delenv("RESET_USER_PASSWORD", raising=False)
        User.objects.create_user(username="manager", password="old-pass-12345")

        call_command("bootstrap_admin")

        assert User.objects.get(username="manager").check_password("old-pass-12345")

    def test_the_reset_clears_the_lock_too(self, monkeypatch):
        User.objects.create_user(username="manager", password="old-pass-12345")
        _attempt("manager")
        monkeypatch.setenv("RESET_USER_USERNAME", "manager")
        monkeypatch.setenv("RESET_USER_PASSWORD", "new-pass-12345")

        call_command("bootstrap_admin")

        assert AccessAttempt.objects.filter(username="manager").count() == 0
