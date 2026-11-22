"""A first manager account, so a fresh — or locked-out — install has a door.

Only the PBKDF2 hash is stored here; the plaintext was handed to the owner once.
Changing the password from ``/users/`` replaces the hash and makes this entry
inert, so this is a bootstrap, not a backdoor that stays usable.

The account is created ONLY when the username does not exist. An existing
account is never touched: a redeploy must not reset a password that somebody
set in the UI.
"""

from django.contrib.auth.models import Group, User

from .audit import record
from .models import AuditEvent

SEED_USERNAME = "sysadmin"
SEED_PASSWORD_HASH = (
    "pbkdf2_sha256$1500000$JCCnj6RHW3yYGDXQj00aQE$"
    "IAKGLLDrXtSAzvyXXgxWYzgldQDaS3D4fh3id+alo8k="
)
SEED_GROUP = "managers"


def ensure_seed_account(stdout=None):
    """Create the bootstrap manager if it is absent. Returns True when created."""
    if User.objects.filter(username=SEED_USERNAME).exists():
        if stdout:
            stdout("bootstrap: '%s' already exists, left unchanged." % SEED_USERNAME)
        return False

    user = User(username=SEED_USERNAME)
    # Assigning the encoded hash keeps the plaintext out of this file.
    user.password = SEED_PASSWORD_HASH
    user.is_active = True
    user.is_staff = True
    user.save()

    group, _ = Group.objects.get_or_create(name=SEED_GROUP)
    user.groups.add(group)

    record(
        action=AuditEvent.USER_CREATED,
        entity="user",
        entity_id=user.pk,
        description=f"{SEED_USERNAME} · bootstrap manager account",
    )
    if stdout:
        stdout(f"bootstrap: created manager account '{SEED_USERNAME}'.")
    return True
