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
    # --- one account, one phone ------------------------------------------
    "Phone bound to": "الهاتف المرتبط",
    "Any phone": "أي هاتف",
    "Clear the phone": "مسح الجهاز",
    "Clear the phone this account is bound to? The old phone stops working at once.":
        "تمسح الهاتف المرتبط بالحساب؟ الهاتف القديم هيقف عن العمل فورًا.",
    "The device was cleared from %(name)s. They can sign in on a new phone now.":
        "تم مسح الجهاز من حساب %(name)s. يقدر يدخل من هاتف جديد الآن.",
    "%(name)s was not bound to any phone.": "حساب %(name)s مش مرتبط بأي هاتف.",
    "Phone unbound from the app": "فك ارتباط الهاتف بالتطبيق",
    # --- the Android page: the build, and the people who use it -----------
    "The build on the phones, and the people who sign in from them.":
        "النسخة اللي على الموبايلات، والناس اللي بتدخل منها.",
    "App users": "مستخدمو التطبيق",
    "Automatic": "تلقائي",
    "Nobody sends a file or a link: an installed app asks this server for the newest build when it opens, and every six hours while it is closed. A new build is offered to the phone, downloaded and installed after one confirmation.":
        "مش حد بيبعت ملف ولا لينك: التطبيق المثبَّت بيسأل السيرفر عن أحدث نسخة لما يتفتح، وكل ست ساعات وهو مقفول. النسخة الجديدة تظهر على الموبايل، وتنزّل وتتثبّت بعد تأكيد واحد.",
    "The list of published builds could not be read just now.":
        "مش قادرين نقرأ قائمة النسخ المنشورة دلوقتي.",
    "GitHub refused the request for now (its hourly limit). The phones are offered the last build this server has seen; it catches up by itself.":
        "GitHub رفض الطلب مؤقتًا (حد الساعة). الموبايلات بتعرض لها آخر نسخة شافها السيرفر، ويرجع يتظبط لوحده.",
    "The server could not reach GitHub. The phones are offered the last build this server has seen.":
        "السيرفر مش قادر يوصل GitHub. الموبايلات بتعرض لها آخر نسخة شافها السيرفر.",
    "GitHub answered with something unexpected. The phones are offered the last build this server has seen.":
        "GitHub رد بحاجة غير متوقعة. الموبايلات بتعرض لها آخر نسخة شافها السيرفر.",
    "From then on the app updates itself: this link is only needed for a new phone.":
        "من بعد كده التطبيق بيحدّث نفسه: اللينك ده للموبايل الجديد بس.",
    "A warehouse manager publishes the build from the advanced options below.":
        "مدير المخزن بينشر النسخة من الخيارات المتقدمة تحت.",
    "User name": "اسم الدخول",
    "Phone": "الهاتف",
    "Last sign-in": "آخر دخول",
    "App only": "من التطبيق فقط",
    "Closed": "مغلق",
    "No one signs in from the app yet.": "مفيش حد بيدخل من التطبيق لحد دلوقتي.",
    "Add a user below: the phone number is what they sign in with.":
        "أضف مستخدم تحت: رقم الهاتف هو اللي بيدخل بيه.",
    "Add an app user": "إضافة مستخدم للتطبيق",
    "The phone number is the identity: the app signs in with it (or with the user name), and the web form can be closed to this account.":
        "رقم الهاتف هو الهوية: التطبيق بيدخل بيه (أو باسم الدخول)، وممكن تقفل دخول الويب للحساب ده.",
    "Left empty, it is taken from the phone number.": "لو سيبتها فاضية، بتتاخد من رقم الهاتف.",
    "For example 01012345678": "مثال: 01012345678",
    "At least %(n)s characters.": "على الأقل %(n)s حروف.",
    "Create the account": "إنشاء الحساب",
    "Previous builds": "نسخ سابقة",
    "Open the link on the phone once and install the file (allow installing apps from this source if the phone asks).":
        "افتح اللينك على الموبايل مرة واحدة وثبّت الملف (اسمح بتثبيت التطبيقات من المصدر ده لو الموبايل سأل).",
    "Sign in with the phone number (or the user name) and the password a manager gave you.":
        "ادخل برقم الهاتف (أو باسم الدخول) والباسورد اللي مدير المخزن أعطاه لك.",
    "Advanced options": "خيارات متقدمة",
    "Additions waiting for approval": "إضافات بانتظار الاعتماد",
    "Approve and move the stock": "اعتماد وترحيل الرصيد",
    "Back": "رجوع",
    "Code": "الكود",
    "Decided by": "اعتمده",
    "Decision note": "ملاحظة القرار",
    "Document date": "تاريخ المستند",
    "From the Android app": "من تطبيق الأندرويد",
    "In stock now": "الرصيد الحالي",
    "Note (optional)": "ملاحظة (اختياري)",
    "Open full size": "فتح بالحجم الكامل",
    "Photo": "صورة",
    "Photographed document": "المستند المصوَّر",
    "Review": "مراجعة",
    "Signed by (engineer)": "اسم المهندس الذي وقّع",
    "Submitted at": "وقت الإرسال",
    "The date written on the paper, not today's date.": "التاريخ المكتوب على الورقة، وليس تاريخ اليوم.",
    "The photographed document": "صورة المستند",
    "The voucher": "بيانات المستند",
    "Used at / installed at": "مكان الاستخدام / التركيب",
    "Voucher number": "رقم المستند",
    "Where the goods go": "أين ستُستخدم البضاعة",
    "Publish a build by hand": "نشر نسخة يدويًا",
    "A build published as a release on %(repo)s is the whole step: nothing has to be typed here. Use the form only to pin a build that is not there yet, or to keep the phones on an older one.":
        "نشر النسخة كـrelease على %(repo)s هو الخطوة كلها: مفيش حاجة تتكتب هنا. استخدم الفورم بس لتثبيت نسخة لسه مش موجودة، أو لتخلي الموبايلات على نسخة أقدم.",
    "The server address is built into the app; there is no field on the phone to change it.":
        "عنوان السيرفر مبني جوّه التطبيق، ومفيش خانة على الموبايل تغيّره.",
    "%(active)s of %(total)s active": "%(active)s نشِط من %(total)s",
    # --- the update arrives from GitHub, not from this page ---------------
    "The update arrives by itself": "التحديث يصل تلقائيًا",
    "Read from GitHub releases": "مقروء من إصدارات GitHub",
    "Read from GitHub": "مقروء من GitHub",
    # --- why a sign-in was refused, and how a manager clears it -----------
    "This account signs in from the phone app only. Open the app, or ask a warehouse manager to allow web sign-in for it.": "الحساب ده بيدخل من تطبيق الموبايل بس. افتح التطبيق، أو اطلب من مدير المخزن يسمح له بالدخول من الويب.",
    "This account is closed. Ask a warehouse manager to reopen it.":
        "الحساب ده مغلق. اطلب من مدير المخزن إعادة فتحه.",
    "Locked": "مقفول",
    "Locked after %(failures)s failed attempts (limit %(limit)s)":
        "مقفول بعد %(failures)s محاولة فاشلة (الحد %(limit)s)",
    "Clear the lockout": "فتح القفل",
    "Lockout cleared": "اتفتح القفل",
    "Password reset on deploy": "إعادة تعيين كلمة المرور عند النشر",
    "The sign-in lockout of %(name)s was cleared. They can sign in now.":
        "اتفتح قفل الدخول للحساب %(name)s. يقدر يدخل دلوقتي.",
    "Sign-in lockout cleared": "فتح قفل الدخول",
    "The server reads the newest build from %(repo)s every ten minutes. Publishing a release there is the whole step: nothing has to be typed on this page, and every phone is offered the new build on its next start.":
        "السيرفر يقرأ آخر بناء من %(repo)s كل عشر دقائق. نشر إصدار جديد هناك هو كل المطلوب: مفيش حاجة تتكتب في الصفحة دي، وكل موبايل بيتعرض عليه البناء الجديد عند أول تشغيل.",
    "Size": "الحجم",
    "Checksum (SHA-256)": "البصمة (SHA-256)",
    "Download": "التحميل",
    "The release list could not be read just now.": "تعذّر قراءة قائمة الإصدارات حاليًا.",
    "The app is being offered the build recorded below instead. This is not an error in the build: the server could not reach GitHub.":
        "التطبيق بيتعرض عليه البناء المسجّل تحت بدلًا منه. ده مش خطأ في البناء: السيرفر مش قادر يوصل GitHub.",
    "GitHub refused the request for now (its hourly limit). The app is offered the last build this server has seen; nothing is lost and it will catch up by itself.":
        "GitHub رفض الطلب مؤقتًا (حد الاستخدام في الساعة). التطبيق بيتعرض عليه آخر بناء شافه السيرفر؛ مفيش حاجة ضاعت والسيرفر هيلحق نفسه لوحده.",
    "The server could not reach GitHub at all. The app is offered the last build this server has seen.":
        "السيرفر مش قادر يوصل GitHub خالص. التطبيق بيتعرض عليه آخر بناء شافه السيرفر.",
    "GitHub answered with something unexpected. The app is offered the last build this server has seen.":
        "GitHub ردّ بردّ غير متوقع. التطبيق بيتعرض عليه آخر بناء شافه السيرفر.",
    "Record a build by hand (fallback)": "تسجيل بناء يدويًا (احتياطي)",
    "Not needed while the list above is readable. Use it to pin a build that is not on GitHub yet, or to keep the phones on an older one.":
        "مش مطلوب طالما القائمة فوق مقروءة. استخدمه لتثبيت بناء لسه مش على GitHub، أو لتثبيت الموبايلات على بناء أقدم.",
    # --- who may sign in where ------------------------------------------
    "This is the last warehouse manager.": "هذا آخر مدير مخزن.",
    "A warehouse worker's account signs in from the phone app only.": "حساب عامل المخزن يعمل على تطبيق الهاتف فقط.",
    # --- the app is tied to its server ---------------------------------
    "Nothing to configure: the app is already tied to this server, and the phone cannot change that address.": "لا شيء يُضبط: التطبيق مربوط بهذا الخادم، ولا يستطيع الهاتف تغيير هذا العنوان.",
    "Server address (fixed in the app)": "عنوان الخادم (مثبَّت في التطبيق)",
    "Built into the app for support only: there is no field on the phone to change it, so a password cannot be sent to another server.": "مثبَّت داخل التطبيق للدعم فقط: لا يوجد حقل في الهاتف لتغييره، فلا يمكن إرسال كلمة المرور إلى خادم آخر.",
    # --- app accounts on /users/ (the phone is the whole account) ------
    "A warehouse worker needs the phone only.": "عامل المخزن يحتاج التطبيق فقط.",
    "App account": "حساب تطبيق",
    "Web account": "حساب ويب",
    "Name": "الاسم",
    "This number is the account. The app cannot change it.": "هذا الرقم هو الحساب نفسه. التطبيق لا يستطيع تغييره.",
    "User name (optional)": "اسم المستخدم (اختياري)",
    "left empty: taken from the phone": "اتركه فارغًا ليُؤخذ من الرقم",
    "Bookkeeping only: the app signs in with the phone.": "للتنظيم فقط: التطبيق يسجّل الدخول بالرقم.",
    "Create the app account": "إنشاء حساب التطبيق",
    "The app account %(name)s was created. They sign in with the phone number.": "تم إنشاء حساب التطبيق %(name)s. يسجّل الدخول برقم الهاتف.",
    "You cannot close your own account.": "لا يمكنك إغلاق حسابك أنت.",
    "The account of %(name)s was reopened.": "أُعيد فتح حساب %(name)s.",
    "The account of %(name)s was closed.": "أُغلق حساب %(name)s.",
    "App only: the web sign-in form refuses this account": "تطبيق فقط: صفحة الدخول على الويب ترفض هذا الحساب",
    "Door": "باب الدخول",
    "App only": "تطبيق فقط",
    "Web and app": "ويب وتطبيق",
    "Web only": "ويب فقط",
    "Close": "إغلاق",
    "Reopen": "إعادة فتح",
    # --- company permits (one issue, several permits) -----------------
    "Company permits": "أذون الصرف",
    "Company permit": "إذن الصرف",
    "Company permits of the issue": "أذون صرف المستند",
    "One issue can be paid against more than one company permit. Record each permit number with its amount, then tick the items that permit covers — a line belongs to one permit.": "الصرفية الواحدة قد تُسدد بأكثر من إذن صرف. سجّل رقم كل إذن ومبلغه، ثم علّم البنود التي يغطيها الإذن — والبند يتبع إذنًا واحدًا.",
    "One issue can be paid against several permits.": "الصرفية الواحدة قد تُسدد بعدة أذون صرف.",
    "Permits and the items each one covers": "الأذون والبنود التي يغطيها كل إذن",
    "Permit number": "رقم الإذن",
    "Permit amount": "مبلغ الإذن",
    "Amount": "المبلغ",
    "Note": "ملاحظة",
    "Items this permit covers": "البنود التي يغطيها هذا الإذن",
    "Items of the issue": "بنود الصرفية",
    "Issue value": "قيمة الصرفية",
    "Permits total": "إجمالي الأذون",
    "Difference (permits − issue)": "الفرق (الأذون − الصرفية)",
    "Lines with no permit": "بنود بلا إذن",
    "No permit": "بلا إذن",
    "Save the permits": "حفظ الأذون",
    "Leave a row blank to ignore it.": "اترك السطر فارغًا لتجاهله.",
    "Back to the report": "رجوع إلى التقرير",
    "Record the permits": "تسجيل الأذون",
    "Issues still missing a company permit": "صرفيات بلا إذن صرف",
    "Record the permits and tick the items each one covers.": "سجّل الأذون وعلّم البنود التي يغطيها كل إذن.",
    "Recorded permits": "الأذون المسجّلة",
    "No company permit is recorded for these issues yet.": "لا يوجد إذن صرف مسجّل لهذه الصرفيات بعد.",
    "No item is ticked under this permit yet.": "لم يُعلَّم أي بند على هذا الإذن بعد.",
    "Company permits and the items each one covers": "أذون الصرف والبنود التي يغطيها كل إذن",
    "Company permits recorded on %(number)s.": "تم تسجيل أذون الصرف على %(number)s.",
    "Only a warehouse manager can record company permits.": "مدير المخزن وحده يسجّل أذون الصرف.",
    "Enter the permit number, or clear the row.": "أدخل رقم الإذن أو افرغ السطر.",
    "Enter the permit amount as a number.": "أدخل مبلغ الإذن كرقم.",
    "The permit amount cannot be negative.": "مبلغ الإذن لا يكون سالبًا.",
    "The permit number is too long.": "رقم الإذن أطول من المسموح.",
    "Permit %(permit)s is listed twice on this document.": "الإذن %(permit)s مكرر على هذا المستند.",
    "Permit %(permit)s is already recorded on %(number)s.": "الإذن %(permit)s مسجّل بالفعل على %(number)s.",
    "A document takes at most %(max)s company permits.": "المستند يأخذ %(max)s إذن صرف كحد أقصى.",
    "Choose a permit of this document for %(sku)s.": "اختر إذنًا من أذون هذا المستند للبند %(sku)s.",
    "Line %(line)s is ticked under more than one permit.": "البند %(line)s معلَّم على أكثر من إذن.",
    "That permit number was just recorded elsewhere.": "رقم الإذن هذا سُجّل للتوّ في موضع آخر.",
    "permits cleared": "أُزيلت الأذون",
    # --- company permits (end) ----------------------------------------
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
    # Sidebar group titles and the missing-paperwork page.
    "Operations": "العمليات",
    "Administration": "الإدارة",
    "Missing paperwork": "الحركات الناقصة",
    "Lines missing paperwork": "بنود ناقصة الورق",
    "Lines to complete": "بنود تحتاج استكمال",
    "Reason": "السبب",
    "All reasons": "كل الأسباب",
    "All sites": "كل المواقع",
    "Clear the filters": "مسح الفلاتر",
    "PO / reference": "أمر الشراء / المرجع",
    "One row per line, not per document.": "سطر لكل بند، لا لكل مستند.",
    "Nothing is missing: every line has its document.": "لا يوجد ناقص: كل بند له مستنده.",
    "A warehouse manager completes this.": "مدير المخزن هو من يكمل هذا.",
    "Only a warehouse manager can complete the paperwork.": "مدير المخزن فقط هو من يكمل الورق.",
    "Every line that moved without its document: no company voucher, a document still waiting for approval, or goods delivered with nothing recording them. Completing a line here removes it.": "كل بند اتحرك من غير ورقته: بلا رقم إذن شركة، أو مستند لسه مستني الاعتماد، أو بضاعة اتسلّمت ومفيش حاجة مسجّلة لها. إكمال البند هنا بيشيله من الصفحة.",
    "Issue not approved — it never reaches the issues report": "صرف لم يُعتمد — لن يظهر في تقرير الصرفيات",
    "Addition not approved — the stock was never increased": "إضافة لم تُعتمد — المخزون لم يزد",
    "Moved with no company voucher number": "تحرّك بلا رقم إذن شركة",
    "Delivered against a purchase order with no company voucher number": "مستلم على أمر شراء بلا رقم إذن شركة",
    "Purchase order delivery": "توريد أمر شراء",
    "Company voucher recorded": "تسجيل رقم إذن الشركة",
    "Issue not approved": "صرف غير معتمد",
    "Addition not approved": "إضافة غير معتمدة",
    "No voucher number": "بلا رقم إذن",
    "Delivery without voucher": "توريد بلا رقم إذن",
    "Enter the company voucher number.": "أدخل رقم إذن الشركة.",
    "The company voucher number is too long.": "رقم إذن الشركة أطول من المسموح.",
    "Voucher %(permit)s is already booked as %(number)s.": "الإذن %(permit)s مسجّل بالفعل على المستند %(number)s.",
    "Voucher %(permit)s is already recorded on the delivery of %(po)s.": "الإذن %(permit)s مسجّل بالفعل على توريد %(po)s.",
    "Voucher %(permit)s was just booked on another document.": "الإذن %(permit)s سُجّل للتوّ على مستند آخر.",
    "Voucher recorded on %(number)s.": "تم تسجيل الإذن على %(number)s.",
    "Voucher recorded on the delivery of %(po)s.": "تم تسجيل الإذن على توريد %(po)s.",
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
    # Every module is scanned, not a hand-kept list: a module left out of the
    # list would ship English on the Arabic interface and nothing would
    # complain. ``_()`` and ``_lazy()`` both mark a translatable string.
    for path in sorted((BASE_DIR / "stock_manager").glob("*.py")):
        text = path.read_text(encoding="utf-8")
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

ARABIC.update({
    'Build number': 'رقم البناء',
    'Checksum (SHA-256)': 'بصمة الملف (SHA-256)',
    'Current phone': 'الرقم الحالي',
    'Enter the build number (a whole number that only grows).': 'أدخل رقم البناء (رقم صحيح يزيد فقط).',
    'File size (bytes)': 'حجم الملف (بايت)',
    'Mandatory': 'إلزامي',
    'Mandatory: the app blocks use until this build is installed.': 'إلزامي: يمنع التطبيق الاستخدام حتى تثبيت هذا البناء.',
    'No pending request.': 'لا توجد طلبات معلّقة.',
    'No phone': 'بلا رقم',
    'Phone change decided': 'تم البتّ في طلب تغيير الرقم',
    'Phone change requested': 'طلب تغيير رقم الهاتف',
    'Phone change requests': 'طلبات تغيير رقم الهاتف',
    'Phone the app signs in with': 'رقم الهاتف الذي يدخل به التطبيق',
    'Refuse': 'رفض',
    'Requested phone': 'الرقم المطلوب',
    'Save the phone': 'حفظ الرقم',
    'Sign in with your phone number and the password a manager gave you.': 'سجّل الدخول برقم هاتفك وكلمة المرور التي أعطاها لك المدير.',
    'Sign in with your phone number (or user name) and the password a manager gave you.': 'سجّل الدخول برقم هاتفك (أو اسم المستخدم) وكلمة المرور التي أعطاها لك المدير.',
    'Sign-in phone': 'رقم الدخول',
    'Sign-in phone changed': 'تغيّر رقم الدخول',
    'That request is no longer pending.': 'هذا الطلب لم يعد معلّقًا.',
    'The app cannot change a phone: it asks, a manager decides.': 'التطبيق لا يغيّر رقم الهاتف: يطلب، والمدير يقرر.',
    'The app cannot change this number; only a manager can, here.': 'التطبيق لا يغيّر هذا الرقم؛ يغيّره المدير من هنا فقط.',
    'The app refuses a file whose checksum does not match.': 'يرفض التطبيق أي ملف لا تطابق بصمته.',
    'The build number must be higher than %(code)s, or the phones on that build would not see the update.': 'رقم البناء يجب أن يكون أعلى من %(code)s، وإلا فلن ترى الهواتف التي على ذلك البناء التحديث.',
    'The checksum must be 64 hexadecimal characters.': 'البصمة يجب أن تكون 64 حرفًا سادس عشريًا.',
    'The phone of %(name)s is now %(phone)s.': 'رقم %(name)s أصبح %(phone)s.',
    'The phone of %(name)s was changed to %(phone)s.': 'تم تغيير رقم %(name)s إلى %(phone)s.',
    'The phones compare this number with their own: it must grow with every build.': 'تقارن الهواتف هذا الرقم برقمها: يجب أن يزيد مع كل بناء.',
    'The request of %(name)s was refused.': 'تم رفض طلب %(name)s.',
    'Update': 'تحديث',
    'changed from the users page': 'من صفحة المستخدمين',
    # --- our internal code over several Oracle codes ---------------------
    'Choose an Oracle code.': 'اختر كود أوراكل.',
    'Choose at least one Oracle code.': 'اختر كود أوراكل واحدًا على الأقل.',
    'Codes without an internal code': 'أكواد بلا كود داخلي',
    'Existing internal code (optional)': 'كود داخلي موجود (اختياري)',
    'Group Oracle codes': 'تجميع أكواد أوراكل',
    'Group under a new code': 'تجميع تحت كود جديد',
    'Internal code': 'الكود الداخلي',
    'Internal codes': 'الأكواد الداخلية',
    'Internal item codes': 'أكواد الأصناف الداخلية',
    'Internal total': 'الإجمالي الداخلي',
    'Move to the code above': 'نقل إلى الكود أعلاه',
    'No Oracle code under this internal code.': 'لا يوجد كود أوراكل تحت هذا الكود الداخلي.',
    'No internal codes yet.': 'لا توجد أكواد داخلية بعد.',
    'No items in the catalogue yet.': 'لا توجد أصناف في الدليل بعد.',
    'One code of ours over every Oracle code that names the same item.': 'كود خاص بنا يجمع كل أكواد أوراكل التي تسمّي الصنف نفسه.',
    'Oracle code': 'كود أوراكل',
    'Oracle code moved to another internal code': 'نُقل كود أوراكل إلى كود داخلي آخر',
    'Oracle codes': 'أكواد أوراكل',
    'Oracle codes grouped under an internal code': 'أكواد أوراكل مجمّعة تحت كود داخلي',
    'Some items have no internal code. Run `python manage.py internal_codes` to review them, then `--apply`.': 'بعض الأصناف بلا كود داخلي. شغّل `python manage.py internal_codes` لمراجعتها، ثم `--apply`.',
    'The code %(sku)s does not exist.': 'الكود %(sku)s غير موجود.',
    'The internal code %(code)s does not exist.': 'الكود الداخلي %(code)s غير موجود.',
    'The internal code and its total are merged over the rows that belong to it.': 'الكود الداخلي وإجماليه مدموجان على الصفوف التي تتبعه.',
    'The internal codes and their Oracle codes': 'الأكواد الداخلية وأكواد أوراكل التابعة لها',
    'Tick the codes that name the same item, then put them under one internal code.': 'علّم الأكواد التي تسمّي الصنف نفسه، ثم ضعها تحت كود داخلي واحد.',
    'Unknown codes: %(codes)s': 'أكواد غير موجودة: %(codes)s',
    'Type the internal code you want to move to.': 'اكتب الكود الداخلي الذي تريد النقل إليه.',
    'The selected codes are now under internal code %(code)s.': 'الأكواد المحددة أصبحت تحت الكود الداخلي %(code)s.',
    'Internal code %(code)s was created for the selected codes.': 'أُنشئ الكود الداخلي %(code)s للأكواد المحددة.',
})



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
