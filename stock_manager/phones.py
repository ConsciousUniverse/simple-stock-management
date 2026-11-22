"""Phone numbers as identities: one canonical form, one validity rule.

The Android app signs in with a phone number, so the number is an identity and
not a label. The same person typing ``+20 101 234 5678``, ``00201012345678`` or
``01012345678`` must resolve to ONE account — otherwise a typo silently becomes
a second identity, and a stock movement is attributed to a number nobody
verified.

Kept free of Django imports so the models, the API and the tests can all use it
without a cycle.
"""

import re

#: A phone is 8–15 digits (E.164 allows at most 15). Below 8 it is a local
#: extension, not a phone anyone can sign in with.
MIN_DIGITS = 8
MAX_DIGITS = 15

#: Anything that is not a digit: spaces, dashes, brackets, a leading +, and the
#: invisible bidi marks an Arabic keyboard or a copy-paste can carry.
_NON_DIGITS = re.compile(r"\D+")

#: Egyptian mobile numbers are written locally as 01x xxxx xxxx (11 digits) and
#: internationally as 201x xxxx xxxx. Both are the same subscriber.
_EGYPT_LOCAL = re.compile(r"^01\d{9}$")


def canonical_phone(value) -> str:
    """The digits of a phone, with the country code spelled one way."""
    digits = _NON_DIGITS.sub("", str(value or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    if _EGYPT_LOCAL.match(digits):
        digits = "20" + digits[1:]
    return digits


def is_valid_phone(value) -> bool:
    return MIN_DIGITS <= len(canonical_phone(value)) <= MAX_DIGITS


def display_phone(value) -> str:
    """The number as a person reads it back: +201012345678."""
    canonical = canonical_phone(value)
    return f"+{canonical}" if canonical else ""


def masked_phone(value) -> str:
    """Enough to recognise your own number, not enough to copy someone else's."""
    canonical = canonical_phone(value)
    if len(canonical) <= 4:
        return canonical
    return f"{'*' * (len(canonical) - 4)}{canonical[-4:]}"
