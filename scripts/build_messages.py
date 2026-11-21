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
    "Sections of this page": "أقسام هذه الصفحة",
    "Edit lock: %(state)s": "قفل التعديل: %(state)s",
    "off": "مُعطَّل",
    "on": "مُفعَّل",
    "Mail receiver": "بريد الاستلام",
    "A durable address, not a file on this server: the server's disk is wiped on every deploy.": 'عنوان دائم وليس ملفًّا على هذا الخادم: قرص الخادم يُمحى مع كل نشر.',
    'A warehouse manager publishes the download address below.': 'مدير المخزن هو من ينشر عنوان التنزيل أدناه.',
    'API address': 'عنوان الواجهة (API)',
    'Accounts': 'الحسابات',
    'Action': 'الإجراء',
    'Active': 'نشط',
    'All areas': 'كل المجالات',
    'Android app': 'تطبيق الأندرويد',
    'App release published': 'نشر إصدار للتطبيق',
    'Area': 'المجال',
    'Audit log': 'سجل التدقيق',
    'Barcode printing': 'طباعة الباركود',
    'Change the password': 'تغيير كلمة السر',
    'Choose the items': 'اختر الأصناف',
    'Choose the items, then print their labels.': 'اختر الأصناف ثم اطبع ملصقاتها.',
    'Create the user': 'إنشاء المستخدم',
    'Current': 'الحالي',
    'Current version': 'الإصدار الحالي',
    'Dashboard': 'لوحة التحكم',
    'Details': 'التفاصيل',
    'Document approved': 'اعتماد مستند',
    'Document created': 'إنشاء مستند',
    'Document number, item code, wording': 'رقم المستند أو كود الصنف أو نص',
    'Document rejected': 'رفض مستند',
    'Download': 'تنزيل',
    'Download address': 'عنوان التنزيل',
    'Email': 'البريد الإلكتروني',
    'Enter a user name.': 'أدخل اسم المستخدم.',
    'Enter the version.': 'أدخل الإصدار.',
    'Events': 'الأحداث',
    'Every recorded action: who did what, and when.': 'كل إجراء مسجل: من فعله ومتى.',
    'Filter': 'تصفية',
    'First name': 'الاسم الأول',
    'Inactive': 'غير نشط',
    'Install the app': 'تنصيب التطبيق',
    'Item changed': 'تعديل صنف',
    'Item created': 'إضافة صنف',
    'Item deleted': 'حذف صنف',
    'Last name': 'الاسم الأخير',
    'Last sign-in': 'آخر دخول',
    'Name': 'الاسم',
    'New user': 'مستخدم جديد',
    'Next': 'التالي',
    'No accounts yet.': 'لا توجد حسابات بعد.',
    'No build has been published yet.': 'لم يُنشر أي إصدار بعد.',
    'No events match this filter.': 'لا توجد أحداث تطابق هذا التصفي.',
    'No release notes.': 'لا توجد ملاحظات للإصدار.',
    'Only a warehouse manager can open this page.': 'مدير المخزن وحده هو من يفتح هذه الصفحة.',
    'Only a warehouse manager can publish a build.': 'مدير المخزن وحده هو من ينشر إصدارًا.',
    'Open': 'فتح',
    'Open the download link on the phone and install the file (allow installing apps from this source if the phone asks).': 'افتح رابط التنزيل على الهاتف ونصّب الملف (واسمح بتثبيت التطبيقات من هذا المصدر إذا طلب الهاتف).',
    'Previous': 'السابق',
    'Publish': 'نشر',
    'Publish a build': 'نشر إصدار',
    'Published': 'تاريخ النشر',
    'Published builds': 'الإصدارات المنشورة',
    'Release notes': 'ملاحظات الإصدار',
    'Role': 'الدور',
    'Save the user': 'حفظ المستخدم',
    'Server address': 'عنوان الخادم',
    'Settings': 'الإعدادات',
    'Settings changed': 'تغيير الإعدادات',
    'Sign in with the same user name and password you use here.': 'سجّل الدخول بنفس اسم المستخدم وكلمة السر التي تستخدمها هنا.',
    'Sign-in': 'تسجيل الدخول',
    'Sign-in refused': 'رفض تسجيل الدخول',
    'Signed in': 'تسجيل دخول',
    'Signed out': 'تسجيل خروج',
    'Spreadsheet exported': 'تصدير جدول',
    'Spreadsheet imported': 'استيراد جدول',
    'Spreadsheets': 'الجداول',
    'That user does not exist.': 'هذا المستخدم غير موجود.',
    'That user name is already taken.': 'اسم المستخدم مستخدم بالفعل.',
    'That version is already published.': 'هذا الإصدار منشور بالفعل.',
    'The account may sign in': 'الحساب مسموح له بتسجيل الدخول',
    'The app reads the server address from the field below; it is already set for this deployment.': 'يقرأ التطبيق عنوان الخادم من الحقل أدناه، وهو مضبوط لهذا النشر بالفعل.',
    'The app uses this address to reach the warehouse data.': 'يستخدم التطبيق هذا العنوان للوصول إلى بيانات المخزن.',
    'The build to install on the phone, and how it connects to this server.': 'الإصدار الذي يُنصَّب على الهاتف، وكيف يتصل بهذا الخادم.',
    'The build was published.': 'تم نشر الإصدار.',
    'The download address must start with https:// or with /.': 'يجب أن يبدأ عنوان التنزيل بـ https:// أو بـ /.',
    'The password must be at least %(n)s characters.': 'يجب أن تكون كلمة السر %(n)s أحرف على الأقل.',
    'The password was changed.': 'تم تغيير كلمة السر.',
    'The user was created.': 'تم إنشاء المستخدم.',
    'The user was saved.': 'تم حفظ المستخدم.',
    'Transfer dispatched': 'تنفيذ تحويل',
    'Transfer requested': 'طلب تحويل',
    'Transfers': 'التحويلات',
    'User': 'المستخدم',
    'User changed': 'تعديل مستخدم',
    'User created': 'إنشاء مستخدم',
    'User deactivated': 'إيقاف مستخدم',
    'User name': 'اسم المستخدم',
    'Users': 'المستخدمون',
    'Version': 'الإصدار',
    'When': 'التاريخ والوقت',
    'Who may sign in, and what each person may do.': 'من يستطيع تسجيل الدخول، وماذا يستطيع كل شخص فعله.',
    'accounts': 'حساب',
    'events': 'حدث',
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
    # The dashboard's overview cards and quick links.
    "A request appears here when a site asks for stock.": "يظهر الطلب هنا عندما يطلب أحد المواقع أصنافًا.",
    "Every movement, by period": "كل حركة خلال فترة محددة.",
    "Issue stock to a site or send it back": "صرف أصناف إلى موقع أو إرجاعها.",
    "Maintain the catalogue and the quantities": "تحديث دليل الأصناف والكميات.",
    "No site requests are waiting": "لا توجد طلبات مواقع في الانتظار.",
    "Print a label sheet for the items you pick": "طبع ورقة ملصقات للأصناف التي تختارها.",
    "Receive a purchase order or a return": "استلام أمر شراء أو مرتجع.",
    "Send my request": "إرسال طلبي.",
    "What the sites asked for, and what is still to dispatch": "ما طلبته المواقع وما زال في انتظار الصرف.",
    "Where to go next": "إلى أين تتجه.",
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
    for name in (
        "ui_strings.py",
        "views.py",
        "barcodes.py",
        "pages.py",
        "models.py",
        "documents.py",
    ):
        text = (BASE_DIR / "stock_manager" / name).read_text(encoding="utf-8")
        # ``_()`` and ``_lazy()`` both mark a translatable string.
        for match in re.finditer(r'_(?:lazy)?\(\s*(["\'])(.+?)\1\s*\)', text, re.S):
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

# Strings of the stock-document pages (additions, issues, the report).
ARABIC.update(
    {
        "A purchase order from a supplier, a transfer in from another project, or goods returned from a site.": "أمر شراء من مورد، أو تحويل وارد من مشروع آخر، أو ارتجاع بضاعة من الموقع.",
        "A voucher number is booked once: the same number cannot move stock twice.": "رقم الإذن يُسجَّل مرة واحدة: لا يمكن لنفس الرقم أن يحرّك المخزون مرتين.",
        "Active items": "أصناف نشطة",
        "Additions": "الإضافة",
        "Additions to the warehouse": "إضافة إلى المخزن",
        "Approve": "اعتماد",
        "Approved": "معتمد",
        "Approved by": "اعتمده",
        "Barcode": "الباركود",
        "By": "بواسطة",
        "By day": "حسب اليوم",
        "By site": "حسب الموقع",
        "Change the dates or record an issue first.": "غيّر التواريخ أو سجّل إذن صرف أولًا.",
        "Choose the site": "اختر الموقع",
        "Choose the type of addition.": "اختر نوع الإضافة.",
        "Choose the type of issue.": "اختر نوع الصرف.",
        "Company voucher number": "رقم إذن الشركة",
        "Day": "اليوم",
        "Decision": "القرار",
        "Description (for a new item)": "الوصف (للصنف الجديد)",
        "Document": "الإذن",
        "Document %(number)s approved and the stock was moved.": "تم اعتماد الإذن %(number)s وتحرّك المخزون.",
        "Document %(number)s rejected; nothing was moved.": "تم رفض الإذن %(number)s ولم يتحرك أي مخزون.",
        "Document %(number)s was saved and is waiting for a warehouse manager to approve it.": "تم حفظ الإذن %(number)s وهو في انتظار اعتماد أمين المخزن.",
        "Document %(number)s was saved and the stock was moved.": "تم حفظ الإذن %(number)s وتحرّك المخزون.",
        "Document not found.": "الإذن غير موجود.",
        "Document type": "نوع الإذن",
        "Documents": "الأذون",
        "Everything that left the warehouse in the chosen period: what, to where, and who sent it.": "كل ما خرج من المخزن في الفترة المختارة: ماذا، وإلى أين، ومن صرفه.",
        "From": "من",
        "Issue documents": "أذون الصرف",
        "Issue stock to a site, transfer it to another project, or reject it and return it to the supplier.": "صرف مخزون لموقع، أو تحويله لمشروع آخر، أو رفضه وإعادته للمورد.",
        "Issued by": "صرفه",
        "Issued lines": "البنود المصروفة",
        "Issues": "الصرف",
        "Issues from the warehouse": "الصرف من المخزن",
        "Issues report": "الصرفيات",
        "Label": "ملصق",
        "Leave empty if the app is the only record": "اتركه فارغًا إذا كان التطبيق هو السجل الوحيد",
        "Lines": "البنود",
        "Log off": "تسجيل الخروج",
        "New addition": "إضافة جديدة",
        "New issue": "صرف جديد",
        "No additions yet.": "لا توجد إضافات بعد.",
        "No issues yet.": "لا توجد أذون صرف بعد.",
        "No items match this search.": "لا توجد أصناف مطابقة لهذا البحث.",
        "No stock has been issued to a site yet.": "لم يُصرف مخزون لأي موقع بعد.",
        "Nothing was issued in this period.": "لم يُصرف شيء في هذه الفترة.",
        "Only a warehouse manager can approve documents.": "اعتماد الأذون متاح لأمين المخزن فقط.",
        "Pages": "الصفحات",
        "Unit": "الوحدة",
        "e.g. piece, metre, kg": "مثال: قطعة، متر، كجم",
        "Pending approval": "في انتظار الاعتماد",
        "Purchase order / reference": "أمر الشراء / المرجع",
        "Qty": "الكمية",
        "Quantity on hand": "الكمية المتاحة",
        "Recent additions": "أحدث الإضافات",
        "Recent issues": "أحدث أذون الصرف",
        "Reference": "المرجع",
        "Reject": "رفض",
        "Rejected": "مرفوض",
        "Remove line": "حذف السطر",
        "Save the addition": "حفظ الإضافة",
        "Save the issue": "حفظ الصرف",
        "Search": "بحث",
        "Search by item code or description": "ابحث بكود الصنف أو الوصف",
        "Selling price": "سعر البيع",
        "Showing up to 300 items": "يُعرض حتى 300 صنف",
        "Site / project": "الموقع / المشروع",
        "Site / supplier": "الموقع / المورد",
        "Site stock": "مخزون المواقع",
        "Stock goes IN": "المخزون يدخل",
        "Stock goes OUT": "المخزون يخرج",
        "Submitted by": "قدّمه",
        "Supplier / other project": "المورد / المشروع الآخر",
        "Supplier or project name": "اسم المورد أو المشروع",
        "To": "إلى",
        "Total quantity": "إجمالي الكمية",
        "Total value": "إجمالي القيمة",
        "Type": "النوع",
        "Unknown action.": "إجراء غير معروف.",
        "Value": "القيمة",
        "Waiting for approval": "في انتظار الاعتماد",
        "Warehouse": "المخزن",
        "What the warehouse holds, and what each site already holds.": "ما يحتفظ به المخزن، وما يحتفظ به كل موقع.",
        "Your entry is saved for a warehouse manager to approve; the stock moves after approval.": "يُحفظ إدخالك ليعتمده أمين المخزن؛ ولا يتحرك المخزون إلا بعد الاعتماد.",
        # Document-type labels: read from the model's choices, so they are not
        # literal msgids in the source.
        "Purchase order receipt": "توريد بأمر شراء",
        "Transfer in from another project": "تحويل وارد من مشروع آخر",
        "Return from site to warehouse": "ارتجاع من الموقع إلى المخزن",
        "Issue to site": "صرف لموقع",
        "Transfer out to another project": "تحويل لمشروع آخر",
        "Rejected / returned to supplier": "مرفوض / مرتجع للمورد",
    }
)


def main():
    msgids = collect_msgids()
    missing = [msgid for msgid in msgids if msgid not in ARABIC]
    if missing:
        print(json.dumps(missing, ensure_ascii=False, indent=2))
        print(f"{len(missing)} msgid(s) have no Arabic translation", file=sys.stderr)
        return 1
    LOCALE_DIR.mkdir(parents=True, exist_ok=True)
    # Choice labels and other dynamic strings are not literal msgids in the
    # source, so the catalog is the union: a translated label can then never
    # fall back to English on the Arabic interface.
    msgids = sorted(set(msgids) | set(ARABIC))
    write_po(msgids)
    write_mo(msgids)
    print(f"wrote {len(msgids)} translations to {LOCALE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
