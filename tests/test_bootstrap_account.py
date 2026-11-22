"""The bootstrap manager: created once, never overwriting anybody."""

import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.management import call_command

from stock_manager.bootstrap_account import SEED_USERNAME
from stock_manager.models import AuditEvent

pytestmark = pytest.mark.django_db

PASSWORD = "Orascom#vdQg0jxAOtyA"


def test_the_deploy_creates_the_manager_account():
    call_command("bootstrap_admin")

    user = User.objects.get(username=SEED_USERNAME)
    assert user.is_active and user.is_staff
    assert user.groups.filter(name="managers").exists()


def test_the_password_verifies_against_the_stored_hash(settings):
    # The suite hashes with MD5 for speed; production uses PBKDF2, which is what
    # the seeded hash is written in. Verify it under the production list.
    settings.PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.PBKDF2PasswordHasher",
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ]
    call_command("bootstrap_admin")

    assert authenticate(username=SEED_USERNAME, password=PASSWORD) is not None


def test_a_second_deploy_does_not_reset_the_password(settings):
    settings.PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.PBKDF2PasswordHasher",
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ]
    call_command("bootstrap_admin")
    user = User.objects.get(username=SEED_USERNAME)
    user.set_password("changed-in-the-ui-123")
    user.save()

    call_command("bootstrap_admin")

    assert authenticate(username=SEED_USERNAME, password=PASSWORD) is None
    assert authenticate(username=SEED_USERNAME, password="changed-in-the-ui-123")


def test_it_is_audited_once():
    call_command("bootstrap_admin")
    call_command("bootstrap_admin")

    rows = AuditEvent.objects.filter(action=AuditEvent.USER_CREATED)
    assert rows.count() == 1


def test_the_plaintext_is_not_in_the_source():
    from pathlib import Path

    source = Path("stock_manager/bootstrap_account.py").read_text(encoding="utf-8")
    assert PASSWORD not in source
