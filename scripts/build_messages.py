"""Build the Arabic translation catalog without gettext.

The deployment image has no ``gettext`` binaries (``msgfmt``/``xgettext``), so
this script extracts the msgids from the templates and the Python modules, pairs
them with the Arabic strings below and writes both the ``.po`` (readable, under
version control) and the compiled ``.mo`` (what Django loads).

Run it after adding a translatable string:

    python scripts/build_messages.py

It exits non-zero when a msgid has no Arabic translation, so a missing string
cannot ship as English on the Arabic interface.
"""

import json
import re
import struct
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOCALE_DIR = BASE_DIR / "locale" / "ar" / "LC_MESSAGES"

ARABIC = {
    "Account temporarily locked": "الحساب مقفل مؤقتًا",
    "Actions": "إجراءات",
    "Active item codes": "أكواد أصناف نشطة",
    "Add a new item code to the warehouse catalogue": "إضافة كود صنف جديد إلى دليل المخزن",
    "Add an item to the warehouse first.": "أضف صنفًا إلى المخزن أولًا.",
    "Add at least one item to receive.": "أضف صنفًا واحدًا على الأقل للاستلام.",
    "Add item": "إضافة صنف",
    "Add line": "إضافة سطر",
    "Adjust your search or add a new item code.": "عدّل البحث أو أضف كود صنف جديد.",
    "An unexpected error occurred while issuing the stock.": "حدث خطأ غير متوقع أثناء صرف المخزون.",
    "An unexpected error occurred while receiving the delivery.": "حدث خطأ غير متوقع أثناء استلام التوريد.",
    "Apply": "تطبيق",
    "Authorised users only. Accounts are created by the system administrator.": "للمستخدمين المصرح لهم فقط. الحسابات تُنشأ بواسطة مسؤول النظام.",
    "Awaiting dispatch": "في انتظار الصرف",
    "Back to dashboard": "العودة إلى لوحة التحكم",
    "Back to sign in": "العودة لتسجيل الدخول",
    "Barcode labels": "ملصقات الباركود",
    "Book the delivery against the purchase order number; the quantities are added to the warehouse.": "سجّل التوريد على رقم أمر الشراء؛ تُضاف الكميات إلى المخزن.",
    "Cancel": "إلغاء",
    "Cancel the request": "إلغاء الطلب",
    "Change my password": "تغيير كلمة المرور",
    "Change password": "تغيير كلمة المرور",
    "Choose a file": "اختر ملفًا",
    "Clear": "مسح",
    "Close": "إغلاق",
    "Company item code": "كود الصنف في نظام الشركة",
    "Confirm": "تأكيد",
    "Confirm new password": "تأكيد كلمة المرور الجديدة",
    "Construction sites": "مواقع الإنشاءات",
    "Copies per item": "عدد النسخ لكل صنف",
    "Create warehouse item": "إنشاء صنف بالمخزن",
    "Current password": "كلمة المرور الحالية",
    "Data import / export": "استيراد / تصدير البيانات",
    "Date": "التاريخ",
    "Delete": "حذف",
    "Delete item": "حذف الصنف",
    "Deleted.": "تم الحذف.",
    "Delivery received.": "تم استلام التوريد.",
    "Description": "الوصف",
    "Dispatch": "صرف",
    "Dispatch the request": "صرف الطلب",
    "Dispatched": "تم الصرف",
    "Each receipt line must be an item and a quantity.": "كل سطر استلام يجب أن يحتوي على صنف وكمية.",
    "Edit": "تعديل",
    "Edit item": "تعديل الصنف",
    "Enter a quantity greater than zero.": "أدخل كمية أكبر من صفر.",
    "Enter the purchase order number.": "أدخل رقم أمر الشراء.",
    "Export to Excel": "تصدير إلى Excel",
    "Fill in the required fields.": "أكمل الحقول المطلوبة.",
    "Hide": "إخفاء",
    "Home": "الرئيسية",
    "Import from Excel": "استيراد من Excel",
    "Inventory": "المخزون",
    "Issue": "صرف",
    "Issue stock to a site and it appears here.": "اصرف مخزونًا لموقع وسيظهر هنا.",
    "Issue to site": "صرف لموقع",
    "Issuing stock is disabled while the warehouse is being maintained.": "الصرف معطّل أثناء أعمال الصيانة على المخزن.",
    "Item %(sku)s was not found.": "الصنف %(sku)s غير موجود.",
    "Item code": "كود الصنف",
    "Item not found.": "الصنف غير موجود.",
    "Items": "الأصناف",
    "Key figures": "المؤشرات الرئيسية",
    "Language": "اللغة",
    "Line added.": "تمت إضافة السطر.",
    "Loading...": "جارٍ التحميل...",
    "Log On": "تسجيل الدخول",
    "Log out": "تسجيل الخروج",
    "Maintain item codes, descriptions, prices and quantities": "إدارة أكواد الأصناف والأوصاف والأسعار والكميات",
    "Maintenance mode": "وضع الصيانة",
    "Menu": "القائمة",
    "Move stock from the warehouse to a construction site": "نقل المخزون من المخزن إلى موقع الإنشاءات",
    "Move the catalogue in and out of the system": "إدخال وإخراج دليل الأصناف من النظام",
    "New password": "كلمة المرور الجديدة",
    "New site requests will appear here.": "طلبات المواقع الجديدة ستظهر هنا.",
    "No deliveries have been received yet.": "لم يتم استلام أي توريدات بعد.",
    "No site stock yet": "لا يوجد مخزون بالمواقع بعد",
    "No warehouse items found": "لا توجد أصناف بالمخزن",
    "Notes": "ملاحظات",
    "Nothing awaiting dispatch": "لا يوجد ما ينتظر الصرف",
    "Only a warehouse manager can issue stock to a site.": "أمين المخزن فقط يمكنه الصرف لموقع.",
    "Operational": "يعمل",
    "Optional": "اختياري",
    "Overview": "نظرة عامة",
    "PO number": "رقم أمر الشراء",
    "Password": "كلمة المرور",
    "Password changed": "تم تغيير كلمة المرور",
    "Pending": "قيد الانتظار",
    "Pending issues": "طلبات صرف معلّقة",
    "Please confirm": "برجاء التأكيد",
    "Print": "طباعة",
    "Print a Code 128 label per item. The barcode carries the item code used in the company system.": "اطبع ملصق Code 128 لكل صنف. الباركود يحمل كود الصنف المستخدم في نظام الشركة.",
    "Print labels": "طباعة الملصقات",
    "Purchase order number": "رقم أمر الشراء",
    "Quantity": "الكمية",
    "Receipts (30 days)": "توريدات (30 يومًا)",
    "Receive": "استلام",
    "Receive from supplier (PO)": "استلام من المورد (أمر شراء)",
    "Received by": "استلمه",
    "Receiving (PO)": "الاستلام (أمر شراء)",
    "Receiving is disabled while the warehouse is being maintained.": "الاستلام معطّل أثناء أعمال الصيانة على المخزن.",
    "Recent receipts": "أحدث التوريدات",
    "Refresh": "تحديث",
    "Remove": "حذف",
    "Requests submitted from a site account": "طلبات مقدَّمة من حساب موقع",
    "Retail price": "سعر البيع",
    "Save": "حفظ",
    "Saved.": "تم الحفظ.",
    "Search items by code or description...": "ابحث بالكود أو الوصف...",
    "Search requests...": "ابحث في الطلبات...",
    "Search sites by item code or site...": "ابحث بكود الصنف أو الموقع...",
    "Sections": "الأقسام",
    "Select a site": "اختر موقعًا",
    "Select all": "تحديد الكل",
    "Select an item first.": "اختر صنفًا أولًا.",
    "Select at least one item to label.": "اختر صنفًا واحدًا على الأقل للطباعة.",
    "Select the items to label": "اختر الأصناف المطلوب طباعة ملصقاتها",
    "Show": "إظهار",
    "Sign in": "تسجيل الدخول",
    "Sign in with your username and password": "سجّل الدخول باسم المستخدم وكلمة المرور",
    "Sign-in is paused for this username.": "تسجيل الدخول موقوف مؤقتًا لهذا المستخدم.",
    "Signed in as": "مسجَّل الدخول باسم",
    "Site": "الموقع",
    "Site not found.": "الموقع غير موجود.",
    "Site qty": "كمية الموقع",
    "Site requests awaiting dispatch": "طلبات المواقع في انتظار الصرف",
    "Sites": "المواقع",
    "Sites stock": "مخزون المواقع",
    "Something went wrong.": "حدث خطأ ما.",
    "Status": "الحالة",
    "Stock issued to each construction site": "المخزون المصروف لكل موقع إنشاءات",
    "Stock issued to the site.": "تم صرف المخزون للموقع.",
    "Stock movements are open": "حركة المخزون متاحة",
    "Stock overview": "نظرة عامة على المخزون",
    "Supplier": "المورد",
    "Supplier deliveries": "توريدات الموردين",
    "Supplier name": "اسم المورد",
    "Suppliers · Sites · Inventory": "الموردون · المواقع · المخزون",
    "The file must match the exported layout.": "يجب أن يطابق الملف تنسيق التصدير.",
    "The issued quantity must be a whole number.": "الكمية المصروفة يجب أن تكون رقمًا صحيحًا.",
    "The issued quantity must be greater than zero.": "الكمية المصروفة يجب أن تكون أكبر من صفر.",
    "The item and its stock history will be removed.": "سيتم حذف الصنف وسجل مخزونه.",
    "The limit is {{ failure_limit }} failed attempts. Access is restored automatically once the cool-off period ends.": "الحد هو {{ failure_limit }} محاولة فاشلة. يُستعاد الوصول تلقائيًا بعد انتهاء فترة الانتظار.",
    "The password could not be changed.": "لم يتم تغيير كلمة المرور.",
    "The received quantity must be a whole number.": "الكمية المستلمة يجب أن تكون رقمًا صحيحًا.",
    "The received quantity must be greater than zero.": "الكمية المستلمة يجب أن تكون أكبر من صفر.",
    "The request is withdrawn; no stock moves.": "سيتم سحب الطلب؛ لن تُنقل أي كمية.",
    "The stock leaves the warehouse and moves to the site.": "سيخرج المخزون من المخزن إلى الموقع.",
    "The warehouse is in maintenance mode. Stock movements are disabled.": "المخزن في وضع الصيانة. حركة المخزون معطّلة.",
    "Too many unsuccessful sign-in attempts": "محاولات دخول فاشلة متكررة",
    "Update the description, price and warehouse quantity.": "حدّث الوصف والسعر وكمية المخزن.",
    "Use your new password the next time you sign in.": "استخدم كلمة المرور الجديدة في المرة القادمة.",
    "Username": "اسم المستخدم",
    "Wait for the lock to expire, or ask the system administrator to reset it.": "انتظر انتهاء القفل أو اطلب من مسؤول النظام إعادة ضبطه.",
    "Warehouse and site inventory at a glance": "مخزون المخزن والمواقع في نظرة واحدة",
    "Warehouse items": "أصناف المخزن",
    "Warehouse management": "إدارة المخازن",
    "Warehouse qty": "كمية المخزن",
    "Warehouse status": "حالة المخزن",
    "Warehouse stock": "مخزون المخزن",
    "We could not sign you in.": "تعذّر تسجيل الدخول.",
    "Your password has been updated successfully.": "تم تحديث كلمة المرور بنجاح.",
    "all": "الكل",
    "e.g. NSCOM-1001": "مثال: NSCOM-1001",
    "e.g. PO-2026-00123": "مثال: PO-2026-00123",
    "items": "صنف",
    "selected": "محدد",
    "(.xlsx — the sheet is the source of truth)": "(‎.xlsx — الملف هو مصدر البيانات)",
    "An error occurred.": "حدث خطأ.",
    "Could not add the transfer.": "تعذّرت إضافة طلب النقل.",
    "Could not complete the transfer.": "تعذّر تنفيذ طلب النقل.",
    "Could not create the item.": "تعذّر إنشاء الصنف.",
    "Could not delete the item.": "تعذّر حذف الصنف.",
    "Could not send the transfer request.": "تعذّر إرسال طلب النقل.",
    "Could not update the item.": "تعذّر تحديث الصنف.",
    "Create item": "إنشاء صنف",
    "Delete item?": "حذف الصنف؟",
    "Dismiss notification": "إغلاق التنبيه",
    "Download stock data": "تنزيل بيانات المخزون",
    "Download the current warehouse and site stock.": "نزّل بيانات المخزن والمواقع الحالية.",
    "Enter more than 0!": "أدخل قيمة أكبر من صفر!",
    "Exchange warehouse and site stock as an Excel workbook": "تبادل بيانات المخزن والمواقع في ملف Excel",
    "Export": "تصدير",
    "Failed to upload stock data.": "تعذّر رفع بيانات المخزون.",
    "Hello": "أهلًا",
    "How many?": "كم الكمية؟",
    "Import": "استيراد",
    "Item created successfully.": "تم إنشاء الصنف بنجاح.",
    "Item deleted.": "تم حذف الصنف.",
    "Item qty": "كمية الموقع",
    "Items recorded for your site": "أصناف مسجَّلة لموقعك",
    "License GPLv3": "رخصة GPLv3",
    "No records": "لا توجد سجلات",
    "Not signed in": "غير مسجَّل الدخول",
    "Pause site transfers while the warehouse is maintained": "إيقاف نقل المخزون للمواقع أثناء صيانة المخزن",
    "Please select a file to upload.": "اختر ملفًا للرفع.",
    "Request items from the warehouse to build your site stock.": "اطلب أصنافًا من المخزن لبناء مخزون موقعك.",
    "Requested stock movements between the warehouse and the sites": "حركات المخزون المطلوبة بين المخزن والمواقع",
    "Retail price must be a valid number with up to 2 decimal places.": "سعر البيع يجب أن يكون رقمًا صالحًا بحد أقصى منزلتين عشريتين.",
    "Search site items by code or description...": "ابحث في مخزون الموقع بالكود أو الوصف...",
    "Send transfer request": "إرسال طلب النقل",
    "Shop transfers are paused": "نقل المخزون للمواقع متوقف",
    "Site requests": "طلبات المواقع",
    "Site stock lines": "سطور مخزون المواقع",
    "Site transfer requests are paused until the manager reopens the warehouse.": "طلبات نقل المخزون للمواقع متوقفة حتى يعيد المدير فتح المخزن.",
    "Site user": "مستخدم موقع",
    "Stock currently held by your site": "المخزون الموجود حاليًا في موقعك",
    "Stock data uploaded successfully.": "تم رفع بيانات المخزون بنجاح.",
    "The system is configured to delete all warehouse and site data that is not included in this upload.": "النظام مُهيَّأ لحذف كل بيانات المخزن والمواقع غير المدرجة في هذا الملف.",
    "This action cannot be undone. Continue?": "لا يمكن التراجع عن هذا الإجراء. هل تريد المتابعة؟",
    "Transfer cancelled.": "تم إلغاء طلب النقل.",
    "Transfer dispatched.": "تم صرف طلب النقل.",
    "Transfer qty": "كمية النقل",
    "Transfer request sent to the warehouse.": "تم إرسال طلب النقل إلى المخزن.",
    "Transfers are open": "النقل متاح",
    "Upload anyway": "ارفع على أي حال",
    "Upload stock data": "رفع بيانات المخزون",
    "Warehouse maintenance is in progress.": "صيانة المخزن جارية.",
    "Warehouse manager": "مدير المخزن",
    "pending transfer": "طلب نقل معلّق",
    "pending transfers": "طلبات نقل معلّقة",
    "site stock line": "سطر مخزون موقع",
    "site stock lines": "سطور مخزون المواقع",
    "warehouse item": "صنف بالمخزن",
    "warehouse items": "أصناف بالمخزن",
    "Logout": "تسجيل الخروج",
    "Showing": "عرض",
    "of": "من",
    "Updated": "آخر تحديث",
}


def collect_msgids():
    msgids = set()
    for path in (BASE_DIR / "templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r'{%\s*trans\s+(["\'])(.+?)\1', text, re.S):
            msgids.add(match.group(2))
        for match in re.finditer(
            r"{%\s*blocktrans\s*%}(.+?){%\s*endblocktrans\s*%}", text, re.S
        ):
            msgids.add(" ".join(match.group(1).split()))
        # Runtime messages translated by the page script: tr('...').
        for match in re.finditer(r"\btr\(\s*(['\"])(.+?)\1\s*\)", text):
            msgids.add(match.group(2))
    ui_strings = (BASE_DIR / "stock_manager" / "ui_strings.py").read_text(encoding="utf-8")
    js_block = ui_strings.split("JS_TEXTS = [", 1)[-1].split("]\n", 1)[0]
    for match in re.finditer(r'"((?:[^"\\]|\\.)*)"', js_block):
        msgids.add(match.group(1))
    for name in ("ui_strings.py", "views.py", "barcodes.py"):
        text = (BASE_DIR / "stock_manager" / name).read_text(encoding="utf-8")
        for match in re.finditer(r'_\(\s*(["\'])(.+?)\1\s*\)', text, re.S):
            msgids.add(match.group(2))
    return sorted(msgids)


def write_po(msgids):
    lines = [
        'msgid ""',
        'msgstr ""',
        '"Project-Id-Version: Warehouse management\\n"',
        '"Language: ar\\n"',
        '"MIME-Version: 1.0\\n"',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        '"Plural-Forms: nplurals=6; plural=(n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : '
        'n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5);\\n"',
        "",
    ]
    for msgid in msgids:
        escaped_id = msgid.replace("\\", "\\\\").replace('"', '\\"')
        escaped_str = ARABIC[msgid].replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'msgid "{escaped_id}"')
        lines.append(f'msgstr "{escaped_str}"')
        lines.append("")
    (LOCALE_DIR / "django.po").write_text("\n".join(lines), encoding="utf-8")


#: The header entry of the catalog. ``charset`` is what makes Python decode
#: the Arabic translations; without it gettext falls back to ASCII and raises
#: UnicodeDecodeError the moment the Arabic page is rendered.
MO_HEADER = (
    "Project-Id-Version: Warehouse management\n"
    "Language: ar\n"
    "MIME-Version: 1.0\n"
    "Content-Type: text/plain; charset=UTF-8\n"
    "Content-Transfer-Encoding: 8bit\n"
)


def write_mo(msgids):
    """Write a GNU ``.mo`` file (no plural forms, no context)."""
    entries = [("", MO_HEADER)] + [(msgid, ARABIC[msgid]) for msgid in msgids]
    entries.sort(key=lambda pair: pair[0].encode("utf-8"))

    ids = b""
    strs = b""
    id_table, str_table = [], []
    for msgid, msgstr in entries:
        encoded_id = msgid.encode("utf-8")
        encoded_str = msgstr.encode("utf-8")
        id_table.append((len(encoded_id), len(ids)))
        ids += encoded_id + b"\x00"
        str_table.append((len(encoded_str), len(strs)))
        strs += encoded_str + b"\x00"

    count = len(entries)
    header_size = 7 * 4
    id_table_offset = header_size
    str_table_offset = id_table_offset + count * 8
    ids_offset = str_table_offset + count * 8
    strs_offset = ids_offset + len(ids)

    output = struct.pack(
        "<7I", 0x950412DE, 0, count, id_table_offset, str_table_offset, 0, 0
    )
    for length, offset in id_table:
        output += struct.pack("<2I", length, ids_offset + offset)
    for length, offset in str_table:
        output += struct.pack("<2I", length, strs_offset + offset)
    output += ids + strs
    (LOCALE_DIR / "django.mo").write_bytes(output)


def main():
    msgids = collect_msgids()
    missing = [msgid for msgid in msgids if msgid not in ARABIC]
    if missing:
        print(json.dumps(missing, ensure_ascii=False, indent=2))
        print(f"{len(missing)} msgid(s) have no Arabic translation", file=sys.stderr)
        return 1
    LOCALE_DIR.mkdir(parents=True, exist_ok=True)
    write_po(msgids)
    write_mo(msgids)
    print(f"wrote {len(msgids)} translations to {LOCALE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
