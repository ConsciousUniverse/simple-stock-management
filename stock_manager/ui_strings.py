"""Strings the dashboard script renders at runtime.

They live here rather than in the template so the script can use ``I18N.key``
and the translator catalog (``locale/<lang>/LC_MESSAGES/django.po``) stays the
single source of every translation: each value below is the same ``msgid`` the
templates use, so one entry covers both.
"""

from django.utils.translation import gettext_lazy as _

JS_STRINGS = {
    # Shell
    "appTitle": _("Warehouse management"),
    "appSubtitle": _("Suppliers · Sites · Inventory"),
    "navOverview": _("Overview"),
    "navReceiving": _("Receiving (PO)"),
    "navWarehouse": _("Warehouse stock"),
    "navSites": _("Sites stock"),
    "navIssue": _("Issue to site"),
    "navLabels": _("Barcode labels"),
    "navData": _("Data import / export"),
    "signedInAs": _("Signed in as"),
    "logout": _("Log out"),
    "language": _("Language"),
    "operational": _("Operational"),
    "maintenance": _("Maintenance mode"),
    "maintenanceNotice": _(
        "The warehouse is in maintenance mode. Stock movements are disabled."
    ),
    "stockMovementsOpen": _("Stock movements are open"),
    # Key figures
    "kpiWarehouse": _("Warehouse items"),
    "kpiWarehouseFoot": _("Active item codes"),
    "kpiPending": _("Pending issues"),
    "kpiPendingFoot": _("Awaiting dispatch"),
    "kpiSites": _("Sites"),
    "kpiSitesFoot": _("Construction sites"),
    "kpiReceipts": _("Receipts (30 days)"),
    "kpiReceiptsFoot": _("Supplier deliveries"),
    # Receiving
    "receivingTitle": _("Receive from supplier (PO)"),
    "receivingHint": _(
        "Book the delivery against the purchase order number; the quantities are added to the warehouse."
    ),
    "poNumber": _("Purchase order number"),
    "poNumberPlaceholder": _("e.g. PO-2026-00123"),
    "supplier": _("Supplier"),
    "supplierPlaceholder": _("Supplier name"),
    "notes": _("Notes"),
    "notesPlaceholder": _("Optional"),
    "itemCode": _("Item code"),
    "itemCodePlaceholder": _("Company item code"),
    "description": _("Description"),
    "quantity": _("Quantity"),
    "addLine": _("Add line"),
    "receiveButton": _("Receive"),
    "removeLine": _("Remove"),
    "recentReceipts": _("Recent receipts"),
    "noReceipts": _("No deliveries have been received yet."),
    "colPo": _("PO number"),
    "colSupplier": _("Supplier"),
    "colDate": _("Date"),
    "colItems": _("Items"),
    "colQty": _("Quantity"),
    "colReceivedBy": _("Received by"),
    # Warehouse
    "warehouseTitle": _("Warehouse stock"),
    "warehouseHint": _("Maintain item codes, descriptions, prices and quantities"),
    "addItem": _("Create warehouse item"),
    "addItemHint": _("Add a new item code to the warehouse catalogue"),
    "sku": _("Item code"),
    "skuPlaceholder": _("e.g. NSCOM-1001"),
    "retailPrice": _("Retail price"),
    "addItemButton": _("Add item"),
    "searchWarehouse": _("Search items by code or description..."),
    "colSku": _("Item code"),
    "colDescription": _("Description"),
    "colPrice": _("Retail price"),
    "colWarehouseQty": _("Warehouse qty"),
    "colActions": _("Actions"),
    "edit": _("Edit"),
    "save": _("Save"),
    "cancel": _("Cancel"),
    "delete": _("Delete"),
    "noWarehouseItems": _("No warehouse items found"),
    "noWarehouseHint": _("Adjust your search or add a new item code."),
    "itemCount": _("items"),
    "allItems": _("all"),
    # Sites
    "sitesTitle": _("Sites stock"),
    "sitesHint": _("Stock issued to each construction site"),
    "searchSites": _("Search sites by item code or site..."),
    "colSite": _("Site"),
    "colSiteQty": _("Site qty"),
    "noSitesStock": _("No site stock yet"),
    "noSitesHint": _("Issue stock to a site and it appears here."),
    # Issue
    "issueTitle": _("Issue to site"),
    "issueHint": _("Move stock from the warehouse to a construction site"),
    "site": _("Site"),
    "selectSite": _("Select a site"),
    "issueButton": _("Issue"),
    "pendingTitle": _("Site requests awaiting dispatch"),
    "pendingHint": _("Requests submitted from a site account"),
    "colStatus": _("Status"),
    "statusPending": _("Pending"),
    "statusDispatched": _("Dispatched"),
    "dispatch": _("Dispatch"),
    "cancelIssue": _("Cancel"),
    "noPending": _("Nothing awaiting dispatch"),
    "noPendingHint": _("New site requests will appear here."),
    # Labels
    "labelsTitle": _("Barcode labels"),
    "labelsHint": _(
        "Print a Code 128 label per item. The barcode carries the item code used in the company system."
    ),
    "labelsSelectHint": _("Select the items to label"),
    "copies": _("Copies per item"),
    "printLabels": _("Print labels"),
    "selectAll": _("Select all"),
    "clearSelection": _("Clear"),
    "noItemsToLabel": _("Add an item to the warehouse first."),
    "labelsSelected": _("selected"),
    # Data
    "dataTitle": _("Data import / export"),
    "dataHint": _("Move the catalogue in and out of the system"),
    "exportExcel": _("Export to Excel"),
    "importExcel": _("Import from Excel"),
    "chooseFile": _("Choose a file"),
    "importHelp": _("The file must match the exported layout."),
    # Feedback
    "toastSaved": _("Saved."),
    "toastDeleted": _("Deleted."),
    "toastReceived": _("Delivery received."),
    "toastIssued": _("Stock issued to the site."),
    "toastError": _("Something went wrong."),
    "toastLineAdded": _("Line added."),
    "toastSelectItem": _("Select an item first."),
    "toastInvalidQuantity": _("Enter a quantity greater than zero."),
    "toastRequired": _("Fill in the required fields."),
    "confirmTitle": _("Please confirm"),
    "confirmDelete": _("Delete item"),
    "confirmDeleteBody": _("The item and its stock history will be removed."),
    "confirmDispatch": _("Dispatch the request"),
    "confirmDispatchBody": _("The stock leaves the warehouse and moves to the site."),
    "confirmCancel": _("Cancel the request"),
    "confirmCancelBody": _("The request is withdrawn; no stock moves."),
    "confirm": _("Confirm"),
    "close": _("Close"),
    "loading": _("Loading..."),
    "editItem": _("Edit item"),
    "editItemHint": _("Update the description, price and warehouse quantity."),
}


def js_strings():
    """Resolve every string in the active language for the page script."""
    return {key: str(value) for key, value in JS_STRINGS.items()}

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
