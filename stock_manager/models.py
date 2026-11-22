from django.db import models
from django.contrib.auth.models import User
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _lazy

from .phones import canonical_phone

# Override the __str__ method of the User model to return the username
User.add_to_class("__str__", lambda self: self.username)


class Admin(models.Model):
    edit_lock = models.BooleanField(default=False)
    allow_uploads = models.BooleanField(default=False)
    allow_upload_deletions = models.BooleanField(default=False)
    allow_email_notifications = models.BooleanField(default=False)
    records_per_page = models.IntegerField(default=25, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = "App Configuration"
        verbose_name_plural = "App Configuration"

    # The accessors below must not assume the configuration row exists yet
    # (e.g. on a fresh install); they fall back to the field defaults.

    @staticmethod
    def is_edit_locked():
        config = Admin.objects.first()
        return config.edit_lock if config else False

    @staticmethod
    def is_allow_updoads():
        config = Admin.objects.first()
        return config.allow_uploads if config else False

    @staticmethod
    def is_allow_upload_deletions():
        config = Admin.objects.first()
        return config.allow_upload_deletions if config else False

    @staticmethod
    def is_allow_email_notifications():
        config = Admin.objects.first()
        return config.allow_email_notifications if config else False

    @staticmethod
    def get_records_per_page():
        config = Admin.objects.first()
        return config.records_per_page if config else 25

    def __str__(self):
        return f"Configuration Options"


class Item(models.Model):
    sku = models.CharField(primary_key=True, unique=True, editable=True, max_length=100)
    description = models.CharField(max_length=250)
    retail_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField(validators=[MinValueValidator(0)])
    # Unit of measure as the operator writes it (قطعة / متر / كجم ...). A unit
    # is data, not an enum: the catalogue mixes Arabic and English articles.
    unit = models.CharField(max_length=20, blank=True, default="")
    last_updated = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)  # Soft-delete flag

    def __str__(self):
        return f"{self.sku} ({'Active' if self.is_active else 'Inactive'})"

    def save(self, *args, **kwargs):
        """
        Coerce retail_price to a Decimal with 2 decimal places and validate.
        This handles Decimal representations that may use scientific notation
        (e.g. '0E-2') by converting to a fixed-point string before regex check.
        """
        try:
            dec = Decimal(self.retail_price)
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("Retail price must be a valid number.")

        # Quantize to two decimal places using HALF_UP rounding
        dec = dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Use a fixed-point string representation for validation (avoids scientific notation)
        dec_str = format(dec, 'f')
        if not re.match(r"^\d+(\.\d{1,2})?$", dec_str):
            raise ValueError(
                "Retail price must be a valid number with up to 2 decimal places."
            )

        self.retail_price = dec
        super().save(*args, **kwargs)


class ShopItem(models.Model):
    shop_user = models.ForeignKey(
        User, on_delete=models.CASCADE
    )  # Relates item to a User
    item = models.ForeignKey(
        Item, on_delete=models.SET_NULL, null=True, blank=True
    )  # Relates ShopItem to Item, allows null if Item is deleted
    quantity = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (
            "shop_user",
            "item",
        )  # Ensure unique combination of shop_user and item

    def __str__(self):
        return f"{self.shop_user.username} - {self.item.sku if self.item else 'Item Deleted'}"


class TransferItem(models.Model):
    shop_user = models.ForeignKey(
        User, on_delete=models.CASCADE
    )  # Relates item to a User
    item = models.ForeignKey(
        Item, on_delete=models.CASCADE
    )  # Relates TransferItem to Item without a default value
    quantity = models.IntegerField(default=0)
    ordered = models.BooleanField(default=False)
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.shop_user.username} - {self.item.sku}"


class GoodsReceipt(models.Model):
    """Stock received from a supplier against a purchase order (PO) number.

    A purchase order can arrive in several shipments, so the PO number is not
    unique here: every delivery is its own receipt row.
    """

    po_number = models.CharField(max_length=60)
    supplier = models.CharField(max_length=200, blank=True, default="")
    # The company voucher number for this delivery. Optional at booking time —
    # the goods are on the shelf either way — but a delivery without it cannot
    # be paid, so the reconciliation page lists it until it is filled in.
    external_ref = models.CharField(
        max_length=80, null=True, blank=True, unique=True
    )
    notes = models.TextField(blank=True, default="")
    received_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="receipts"
    )
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-received_at", "-id")
        verbose_name = "Goods receipt (PO)"
        verbose_name_plural = "Goods receipts (PO)"
        indexes = [models.Index(fields=["po_number"])]

    def __str__(self):
        return f"{self.po_number} ({self.received_at:%Y-%m-%d})"

    @property
    def total_quantity(self):
        return sum(line.quantity for line in self.lines.all())


class GoodsReceiptLine(models.Model):
    receipt = models.ForeignKey(
        GoodsReceipt, on_delete=models.CASCADE, related_name="lines"
    )
    item = models.ForeignKey(
        Item,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipt_lines",
    )
    sku = models.CharField(max_length=100)
    description = models.CharField(max_length=250, blank=True, default="")
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    # Snapshot of the unit at booking time: changing the catalogue unit later
    # must not rewrite what a past document said was moved.
    unit = models.CharField(max_length=20, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return f"{self.sku} x{self.quantity}"


class StockDocument(models.Model):
    """A stock movement note (إذن إضافة / إذن صرف) for one counterparty.

    ``direction`` and ``doc_type`` describe WHY stock moves; the movement itself
    happens once, when the document is applied. A document created from the
    mobile app starts ``pending`` and only the web app can approve it, so a
    site user cannot deduct stock on their own.

    ``external_ref`` is the company voucher number. It is unique so a repeated
    mobile submission or an import of the same voucher cannot deduct the same
    quantity twice and unbalance the warehouse.
    """

    IN = "in"
    OUT = "out"
    DIRECTION_CHOICES = ((IN, "Addition"), (OUT, "Issue"))

    PO_RECEIPT = "po_receipt"
    PROJECT_TRANSFER_IN = "project_transfer_in"
    SITE_RETURN = "site_return"
    SITE_ISSUE = "site_issue"
    PROJECT_TRANSFER_OUT = "project_transfer_out"
    SUPPLIER_RETURN = "supplier_return"
    TYPE_CHOICES = (
        (PO_RECEIPT, "Purchase order receipt"),
        (PROJECT_TRANSFER_IN, "Transfer in from another project"),
        (SITE_RETURN, "Return from site to warehouse"),
        (SITE_ISSUE, "Issue to site"),
        (PROJECT_TRANSFER_OUT, "Transfer out to another project"),
        (SUPPLIER_RETURN, "Rejected / returned to supplier"),
    )
    IN_TYPES = (PO_RECEIPT, PROJECT_TRANSFER_IN, SITE_RETURN)
    OUT_TYPES = (SITE_ISSUE, PROJECT_TRANSFER_OUT, SUPPLIER_RETURN)

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = (
        (PENDING, "Pending approval"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    )

    WEB = "web"
    MOBILE = "mobile"
    IMPORT = "import"
    SOURCE_CHOICES = ((WEB, "Web"), (MOBILE, "Mobile app"), (IMPORT, "Import"))

    number = models.CharField(max_length=40, unique=True)
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    doc_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PENDING)
    source = models.CharField(max_length=8, choices=SOURCE_CHOICES, default=WEB)
    site = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_documents",
    )
    counterparty = models.CharField(max_length=200, blank=True, default="")
    reference = models.CharField(max_length=60, blank=True, default="")
    external_ref = models.CharField(
        max_length=80, null=True, blank=True, unique=True
    )
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_stock_documents",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decided_stock_documents",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True, default="")
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "Stock document"
        verbose_name_plural = "Stock documents"
        indexes = [
            models.Index(fields=["doc_type", "status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.number} ({self.get_doc_type_display()})"

    @property
    def type_label(self):
        """The document type in the interface language."""
        return _lazy(self.get_doc_type_display())

    @property
    def is_incoming(self):
        return self.direction == self.IN

    @property
    def is_pending(self):
        return self.status == self.PENDING

    @property
    def total_quantity(self):
        return sum(line.quantity for line in self.lines.all())


class DocumentPermit(models.Model):
    """A company permit (إذن صرف) covering part of one document.

    One issue is often paid against several company permits — the operator's
    rule: an issue dated 1/7 may take permits 050340604, 0503537228 and
    05245322, and each permit names the items it covers. A line therefore
    belongs to at most one permit of its own document, and a permit belongs to
    exactly one document.
    """

    document = models.ForeignKey(
        StockDocument, on_delete=models.CASCADE, related_name="permits"
    )
    # The company's own paper: unique across every document, like a voucher.
    permit_no = models.CharField(max_length=80, unique=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    note = models.CharField(max_length=200, blank=True, default="")
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("id",)
        verbose_name = "Company permit"
        verbose_name_plural = "Company permits"

    def __str__(self):
        return f"{self.permit_no} ({self.document.number})"

    @property
    def total_quantity(self):
        return sum(line.quantity for line in self.lines.all())


class StockDocumentLine(models.Model):
    document = models.ForeignKey(
        StockDocument, on_delete=models.CASCADE, related_name="lines"
    )
    item = models.ForeignKey(
        Item, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    sku = models.CharField(max_length=100)
    description = models.CharField(max_length=250, blank=True, default="")
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    # Snapshot of the unit at booking time: changing the catalogue unit later
    # must not rewrite what a past document said was moved.
    unit = models.CharField(max_length=20, blank=True, default="")
    # Which company permit covers this line, when the issue is split across
    # several of them. Empty means the line is still undocumented.
    permit = models.ForeignKey(
        DocumentPermit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lines",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return f"{self.sku} x{self.quantity}"


class AuditEvent(models.Model):
    """One recorded action: who did what, when.

    ``actor_name`` is a snapshot on purpose. Deleting a user must not turn their
    history anonymous — an audit trail that says "someone" answers nothing.

    No IP address is stored: this project deliberately does not log client IPs
    (see ``AXES_CLIENT_IP_CALLABLE`` in settings), and the audit trail is about
    who changed the stock, not where they sat.
    """

    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    PASSWORD_CHANGED = "password_changed"
    DOCUMENT_CREATED = "document_created"
    DOCUMENT_APPROVED = "document_approved"
    DOCUMENT_REJECTED = "document_rejected"
    DOCUMENT_PERMIT = "document_permit"
    ITEM_CREATED = "item_created"
    ITEM_UPDATED = "item_updated"
    ITEM_DELETED = "item_deleted"
    TRANSFER_SENT = "transfer_sent"
    TRANSFER_COMPLETED = "transfer_completed"
    DATA_IMPORTED = "data_imported"
    DATA_EXPORTED = "data_exported"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DEACTIVATED = "user_deactivated"
    USER_UNLOCKED = "user_unlocked"
    SETTINGS_CHANGED = "settings_changed"
    RELEASE_PUBLISHED = "release_published"
    PHONE_CHANGED = "phone_changed"
    PHONE_REQUESTED = "phone_requested"
    PHONE_REQUEST_DECIDED = "phone_request_decided"

    ACTION_CHOICES = (
        (LOGIN, _lazy("Signed in")),
        (LOGIN_FAILED, _lazy("Sign-in refused")),
        (LOGOUT, _lazy("Signed out")),
        (PASSWORD_CHANGED, _lazy("Password changed")),
        (DOCUMENT_CREATED, _lazy("Document created")),
        (DOCUMENT_APPROVED, _lazy("Document approved")),
        (DOCUMENT_REJECTED, _lazy("Document rejected")),
        (DOCUMENT_PERMIT, _lazy("Company voucher recorded")),
        (ITEM_CREATED, _lazy("Item created")),
        (ITEM_UPDATED, _lazy("Item changed")),
        (ITEM_DELETED, _lazy("Item deleted")),
        (TRANSFER_SENT, _lazy("Transfer requested")),
        (TRANSFER_COMPLETED, _lazy("Transfer dispatched")),
        (DATA_IMPORTED, _lazy("Spreadsheet imported")),
        (DATA_EXPORTED, _lazy("Spreadsheet exported")),
        (USER_CREATED, _lazy("User created")),
        (USER_UPDATED, _lazy("User changed")),
        (USER_DEACTIVATED, _lazy("User deactivated")),
        (SETTINGS_CHANGED, _lazy("Settings changed")),
        (RELEASE_PUBLISHED, _lazy("App release published")),
        (PHONE_CHANGED, _lazy("Sign-in phone changed")),
        (PHONE_REQUESTED, _lazy("Phone change requested")),
        (PHONE_REQUEST_DECIDED, _lazy("Phone change decided")),
    )

    # Grouping for the log's filter: which part of the app an action belongs to.
    AREA_CHOICES = (
        ("auth", _lazy("Sign-in")),
        ("documents", _lazy("Documents")),
        ("items", _lazy("Items")),
        ("transfers", _lazy("Transfers")),
        ("data", _lazy("Spreadsheets")),
        ("users", _lazy("Users")),
        ("settings", _lazy("Settings")),
        ("app", _lazy("Android app")),
    )
    ACTION_AREA = {
        LOGIN: "auth",
        LOGIN_FAILED: "auth",
        LOGOUT: "auth",
        PASSWORD_CHANGED: "auth",
        DOCUMENT_CREATED: "documents",
        DOCUMENT_APPROVED: "documents",
        DOCUMENT_REJECTED: "documents",
        ITEM_CREATED: "items",
        ITEM_UPDATED: "items",
        ITEM_DELETED: "items",
        TRANSFER_SENT: "transfers",
        TRANSFER_COMPLETED: "transfers",
        DATA_IMPORTED: "data",
        DATA_EXPORTED: "data",
        USER_CREATED: "users",
        USER_UPDATED: "users",
        USER_DEACTIVATED: "users",
        USER_UNLOCKED: "users",
        SETTINGS_CHANGED: "settings",
        RELEASE_PUBLISHED: "app",
        PHONE_CHANGED: "users",
        PHONE_REQUESTED: "users",
        PHONE_REQUEST_DECIDED: "users",
    }

    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    actor_name = models.CharField(max_length=150, blank=True, default="")
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    entity = models.CharField(max_length=40, blank=True, default="")
    entity_id = models.CharField(max_length=80, blank=True, default="")
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "Audit event"
        verbose_name_plural = "Audit log"
        indexes = [models.Index(fields=["action", "created_at"])]

    def __str__(self):
        return f"{self.actor_name or '—'} · {self.get_action_display()}"

    @property
    def area(self):
        return self.ACTION_AREA.get(self.action, "")

    @property
    def action_label(self):
        return _lazy(self.get_action_display())


class MobileProfile(models.Model):
    """The phone number a person signs in with in the Android app.

    The phone is the identity in the app and it is deliberately NOT editable
    from the app: a person who changes their SIM asks a warehouse manager, who
    changes it here. An identity the user can rewrite is not an identity — the
    stock movements and the audit trail would then point at a number nobody
    verified.
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="mobile_profile"
    )
    # Canonical digits only (201012345678): the same person typing +20 101…
    # or 0101… must not become two accounts.
    phone = models.CharField(max_length=20, unique=True)
    # An app account exists for the phone and nothing else: the person has no
    # web login, so the web sign-in form refuses them by name instead of letting
    # them into a page they cannot use. Set by a manager on /users/.
    mobile_only = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("phone",)
        verbose_name = "Mobile profile"
        verbose_name_plural = "Mobile profiles"

    def __str__(self):
        return f"{self.user.get_username()} · {self.phone}"

    @staticmethod
    def for_user(user):
        return MobileProfile.objects.filter(user=user).first()

    @staticmethod
    def by_phone(phone):
        canonical = canonical_phone(phone)
        if not canonical:
            return None
        return MobileProfile.objects.select_related("user").filter(phone=canonical).first()


class PhoneChangeRequest(models.Model):
    """A user asking a manager to change the phone they sign in with.

    The request is the ONLY route the app has, and it changes nothing by
    itself: the phone moves when a manager approves, and that approval is what
    the audit trail records.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = (
        (PENDING, _lazy("Pending")),
        (APPROVED, _lazy("Approved")),
        (REJECTED, _lazy("Rejected")),
    )

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="phone_change_requests"
    )
    current_phone = models.CharField(max_length=20, blank=True, default="")
    requested_phone = models.CharField(max_length=20)
    reason = models.TextField(blank=True, default="")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    decided_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decided_phone_requests",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "Phone change request"
        verbose_name_plural = "Phone change requests"
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self):
        return f"{self.user.get_username()} → {self.requested_phone} ({self.status})"

    @staticmethod
    def pending_for(user):
        return PhoneChangeRequest.objects.filter(
            user=user, status=PhoneChangeRequest.PENDING
        ).first()


class MobileSession(models.Model):
    """A signed-in phone: a revocable token, stored as its hash.

    Stateless signed tokens cannot be revoked, and a warehouse phone gets lost.
    Only the SHA-256 of the token is stored, so a database dump cannot be
    replayed as a session.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="mobile_sessions"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    device = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(auto_now=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-last_used_at",)
        verbose_name = "Mobile session"
        verbose_name_plural = "Mobile sessions"

    def __str__(self):
        return f"{self.user.get_username()} · {self.created_at:%Y-%m-%d}"


class AppRelease(models.Model):
    """A published Android build.

    The APK is NOT uploaded here: Render's disk is ephemeral, so a file written
    to MEDIA_ROOT disappears on the next deploy and the download link would rot
    silently. The release stores the address the build is served from instead,
    which survives deploys and can be checked.
    """

    #: Where the row came from: a person typed it, or the server read it from
    #: the published releases. The page labels them, and only a manual row can
    #: be a deliberate pin.
    SOURCE_MANUAL = "manual"
    SOURCE_GITHUB = "github"

    version = models.CharField(max_length=40, unique=True)
    # The app compares THIS number with its own BuildConfig.VERSION_CODE. A
    # version string ("5.3.0") cannot be ordered reliably, and the update
    # decision must be unambiguous.
    version_code = models.PositiveIntegerField(null=True, blank=True, unique=True)
    download_url = models.CharField(max_length=500)
    sha256 = models.CharField(max_length=64, blank=True, default="")
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    # A mandatory build refuses to be skipped: the app blocks use until the
    # operator installs it (a broken client that talks to a changed API).
    mandatory = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default="")
    source = models.CharField(max_length=20, default=SOURCE_MANUAL)
    is_current = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="app_releases",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "App release"
        verbose_name_plural = "App releases"

    def __str__(self):
        return f"{self.version}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_current:
            # Exactly one current build: the app asks "what is the newest one".
            AppRelease.objects.filter(is_current=True).exclude(pk=self.pk).update(
                is_current=False
            )

    @staticmethod
    def latest_manual():
        """The newest build a person recorded, ignoring the published mirror.

        A row recorded before build numbers existed cannot be compared, but it
        must still be visible — the same rule as ``latest()``.
        """
        manual = AppRelease.objects.exclude(source=AppRelease.SOURCE_GITHUB)
        numbered = manual.filter(version_code__isnull=False).order_by("-version_code").first()
        if numbered is not None:
            return numbered
        return manual.filter(is_current=True).first() or manual.first()

    @staticmethod
    def latest():
        """The newest build BY VERSION CODE, which is what the app compares.

        ``is_current`` marks the row the page highlights; it must NOT decide
        what the phones are offered. Publishing a lower build made it current
        and hid the higher one, so a phone two builds behind was told about the
        older of the two.
        """
        newest = (
            AppRelease.objects.filter(version_code__isnull=False)
            .order_by("-version_code")
            .first()
        )
        if newest is not None:
            return newest
        # Releases published before build numbers existed have nothing to
        # compare, but they must still be visible.
        return AppRelease.objects.filter(is_current=True).first() or AppRelease.objects.first()

    def newer_than(self, installed_code):
        return self.version_code is not None and installed_code is not None and (
            self.version_code > installed_code
        )
