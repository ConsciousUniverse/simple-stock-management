from django.db import models
from django.contrib.auth.models import User
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _lazy

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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return f"{self.sku} x{self.quantity}"
