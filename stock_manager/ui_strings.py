"""Strings the dashboard script renders at runtime.

They live here rather than in the template so the script can use ``I18N.key``
and the translator catalog (``locale/<lang>/LC_MESSAGES/django.po``) stays the
single source of every translation: each value below is the same ``msgid`` the
templates use, so one entry covers both.
"""

from django.utils.translation import gettext_lazy as _

#: Runtime messages of the dashboard script. The value is the English text used
#: as the ``msgid`` in the catalog, so the script can translate any literal by
#: its own English wording (``tr('Item deleted.')``).
JS_TEXTS = [
    "An error occurred.",
    "Could not add the transfer.",
    "Could not complete the transfer.",
    "Could not create the item.",
    "Could not delete the item.",
    "Could not send the transfer request.",
    "Could not update the item.",
    "Delete item?",
    "Dismiss notification",
    "Enter more than 0!",
    "Failed to upload stock data.",
    "Hello",
    "How many?",
    "Item created successfully.",
    "Item deleted.",
    "No records",
    "Not signed in",
    "Please confirm",
    "Please select a file to upload.",
    "Retail price must be a valid number with up to 2 decimal places.",
    "Shop transfers are paused",
    "Site user",
    "Stock data uploaded successfully.",
    "The system is configured to delete all warehouse and site data that is not included in this upload.",
    "This action cannot be undone. Continue?",
    "Transfer cancelled.",
    "Transfer dispatched.",
    "Transfer request sent to the warehouse.",
    "Transfers are open",
    "Upload anyway",
    "Warehouse manager",
    "pending transfer",
    "pending transfers",
    "site stock line",
    "site stock lines",
    "warehouse item",
    "warehouse items",
    "Delete",
    "Logout",
    "Log On",
    "Showing",
    "of",
    "Updated",
]


def js_messages():
    """msgid -> translation for the interface language.

    The dashboard script translates a literal by its English text, so the map is
    built from the ``.po`` catalog of the active language: a message added to the
    template is then translatable from the script without a second list. English
    (or a language with no catalog) returns an empty map, which makes ``tr()`` an
    identity function.
    """
    import re
    from pathlib import Path

    from django.conf import settings
    from django.utils.translation import get_language, gettext

    po_path = (
        Path(settings.BASE_DIR) / "locale" / (get_language() or "en") / "LC_MESSAGES" / "django.po"
    )
    if not po_path.exists():
        return {}
    msgids = re.findall(r'^msgid "(.+)"$', po_path.read_text(encoding="utf-8"), re.MULTILINE)
    return {msgid: str(gettext(msgid)) for msgid in msgids if msgid}
