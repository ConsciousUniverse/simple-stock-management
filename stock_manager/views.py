import logging

from django.conf import settings
from django.contrib.auth.views import LoginView
from django.core.exceptions import NON_FIELD_ERRORS
from django.utils.translation import gettext_lazy as _lazy
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.core.paginator import Paginator
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, AllowAny

from .auth import REFUSAL_APP_ONLY, REFUSAL_INACTIVE
from .models import (
    Admin,
    AppRelease,
    AuditEvent,
    GoodsReceipt,
    GoodsReceiptLine,
    Item,
    ShopItem,
    StockDocument,
    StockDocumentLine,
    TransferItem,
)
from . import audit
from .ordering import apply_ordering
from .permissions import is_warehouse_manager
from . import documents as stock_documents
from . import issue_report
from . import reconciliation
from . import permits as company_permits
from .barcodes import BarcodeError, render_barcode_svg
from .ui_strings import js_messages
from .serializers import ItemSerializer, ShopItemSerializer, TransferItemSerializer
from .pagination import CustomPagination
from django.contrib.auth.models import User  # For accessing the User model
from rest_framework.response import (
    Response,
)  # For returning HTTP responses in REST framework
from rest_framework.decorators import api_view, permission_classes
from django.db.models.functions import Lower
from rest_framework import status
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from decimal import Decimal
from django.db.models import F, Q, Sum
from email_service.email import SendEmail
from .utils import SpreadsheetTools

logger = logging.getLogger(__name__)


# API View
class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.filter(is_active=True)
    serializer_class = ItemSerializer
    lookup_field = "sku"
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        queryset = Item.objects.filter(is_active=True)
        search_query = self.request.query_params.get("search", None)
        if search_query:
            queryset = queryset.filter(
                Q(description__icontains=search_query) | Q(sku__icontains=search_query)
            )  # 🔍 Search filter
        return apply_ordering(
            queryset,
            self.request.query_params.get("ordering"),
            natural_key=lambda row: row.sku,
        )

    def create(self, request, *args, **kwargs):
        if not is_warehouse_manager(request.user):
            return Response(
                {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
            )
        sku = request.data.get("sku")
        if sku:
            try:
                item = Item.objects.get(sku=sku)
                if not item.is_active:
                    # Reactivate and update fields
                    serializer = ItemSerializer(item, data=request.data, partial=True)
                    if serializer.is_valid():
                        serializer.save(is_active=True)
                        audit.record(
                            user=request.user,
                            action=AuditEvent.ITEM_CREATED,
                            entity="item",
                            entity_id=sku,
                            description=f"{sku} · {serializer.instance.description}",
                        )
                        return Response(serializer.data, status=status.HTTP_200_OK)
                    else:
                        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                else:
                    return Response({"detail": "Item with this SKU already exists."}, status=status.HTTP_400_BAD_REQUEST)
            except Item.DoesNotExist:
                pass
        response = super().create(request, *args, **kwargs)
        if response.status_code in (200, 201):
            item = response.data
            audit.record(
                user=request.user,
                action=AuditEvent.ITEM_CREATED,
                entity="item",
                entity_id=item.get("sku"),
                description=f"{item.get('sku')} · {item.get('description')}",
            )
        return response

    def update(self, request, *args, **kwargs):
        if not is_warehouse_manager(request.user):
            return Response(
                {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
            )
        sku = request.data.get("sku")
        try:
            item = Item.objects.get(sku=sku)
            if not item.is_active:
                serializer = ItemSerializer(item, data=request.data, partial=True)
                if serializer.is_valid():
                    serializer.save(is_active=True)
                    return Response(serializer.data, status=status.HTTP_200_OK)
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Item.DoesNotExist:
            return Response(
                {"error": "Item not found."}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = ItemSerializer(item, data=request.data, partial=True)
        if serializer.is_valid():
            changed = sorted(serializer.validated_data.keys())
            serializer.save()
            audit.record(
                user=request.user,
                action=AuditEvent.ITEM_UPDATED,
                entity="item",
                entity_id=item.sku,
                description=f"{item.sku} · " + ", ".join(changed),
            )
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        if not is_warehouse_manager(request.user):
            return Response(
                {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
            )
        sku = kwargs.get("sku")
        try:
            item = Item.objects.get(sku=sku)
            item.is_active = False
            item.save()
            # A soft delete: the row stays for the documents that reference it.
            audit.record(
                user=request.user,
                action=AuditEvent.ITEM_DELETED,
                entity="item",
                entity_id=sku,
                description=f"{sku} · {item.description}",
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Item.DoesNotExist:
            return Response({"error": "Item not found."}, status=status.HTTP_404_NOT_FOUND)


class ShopItemViewSet(viewsets.ReadOnlyModelViewSet):
    # Read-only: shop stock is only ever moved via the transfer/complete
    # endpoints, so this collection exposes no write verbs.
    queryset = ShopItem.objects.all()
    serializer_class = ShopItemSerializer
    lookup_field = "item__sku"
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        queryset = ShopItem.objects.filter(shop_user=self.request.user).exclude(item=None)
        search_query = self.request.query_params.get("search", None)
        if search_query:
            queryset = queryset.filter(
                Q(item__description__icontains=search_query)
                | Q(item__sku__icontains=search_query)
            )  # 🔍 Search filter
        return apply_ordering(
            queryset,
            self.request.query_params.get("ordering"),
            natural_key=lambda row: row.item.sku if row.item else "",
        )


class TransferItemViewSet(viewsets.ReadOnlyModelViewSet):
    # Read-only: transfers are created via /api/transfer/ and dispatched or
    # cancelled via /api/complete-transfer/, so this collection exposes no
    # write verbs.
    queryset = TransferItem.objects.all()
    serializer_class = TransferItemSerializer
    lookup_field = "item__sku"
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        user = self.request.user
        if is_warehouse_manager(user):
            queryset = TransferItem.objects.filter(ordered=True)
        else:
            queryset = TransferItem.objects.filter(shop_user=user)
        search_query = self.request.query_params.get("search", None)
        if search_query:
            queryset = queryset.filter(
                Q(item__description__icontains=search_query)
                | Q(item__sku__icontains=search_query)
            )  # 🔍 Search filter
        return apply_ordering(
            queryset,
            self.request.query_params.get("ordering"),
            natural_key=lambda row: row.item.sku,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_edit_lock_status(request):
    if not is_warehouse_manager(request.user):
        return Response(
            {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
        )

    edit_lock_status = request.data.get("edit_lock_status", False)
    admin, created = Admin.objects.get_or_create(id=1)
    admin.edit_lock = edit_lock_status
    admin.save()
    audit.record(
        user=request.user,
        action=AuditEvent.SETTINGS_CHANGED,
        entity="settings",
        entity_id="edit_lock",
        # Read by people, so say what changed in words rather than a field dump.
        description=_("Edit lock: %(state)s")
        % {"state": _("on") if admin.edit_lock else _("off")},
    )
    return Response(
        {"edit_lock": admin.edit_lock},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_edit_lock_status(request):
    return Response({"edit_lock": Admin.is_edit_locked()})


def _site_accounts():
    """The construction sites stock can be issued to (they are user accounts)."""
    return list(
        User.objects.filter(groups__name="shop_users", is_active=True)
        .order_by("username")
        .values("id", "username")
    )


@require_POST
def switch_language(request):
    """Store the chosen interface language and return to the same page.

    Django's own ``set_language`` view re-resolves ``next`` through the URL
    patterns, which sends the dashboard to the API root here, so the redirect
    target is used verbatim (after the usual host check).
    """
    language = request.POST.get("language", "")
    next_url = request.POST.get("next") or "/"
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = "/"
    response = HttpResponseRedirect(next_url)
    if language in dict(settings.LANGUAGES):
        response.set_cookie(
            settings.LANGUAGE_COOKIE_NAME,
            language,
            max_age=settings.LANGUAGE_COOKIE_AGE,
            samesite="Lax",
        )
    return response


# Main Page View
@ensure_csrf_cookie
@login_required
def index(request):
    """The overview: the key figures, the site-request queue, and where to go.

    The tables that do the work live on their own pages; this page states the
    numbers so a reader sees the state of the warehouse without opening them.
    """
    user = request.user
    site_lines = ShopItem.objects.filter(quantity__gt=0)
    transfers = TransferItem.objects.filter(ordered=True)
    if not is_warehouse_manager(user):
        site_lines = site_lines.filter(shop_user=user)
        transfers = transfers.filter(shop_user=user)
    return render(
        request,
        "index.html",
        {
            "js_messages": js_messages(),
            "total_items": Item.objects.filter(is_active=True).count(),
            "site_lines": site_lines.count(),
            "pending_transfers": transfers.count(),
            "edit_locked": Admin.is_edit_locked(),
        },
    )


@api_view(["GET"])
def get_user(request):
    # Ensure the user is authenticated
    if not request.user.is_authenticated:
        return Response(
            {"detail": "Authentication credentials were not provided."}, status=401
        )

    user = request.user
    return Response(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "groups": list(user.groups.values_list("name", flat=True)),
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transfer_item(request):
    if Admin.is_edit_locked():
        logger.debug("Transfer attempt while update mode is enabled.")
        return Response(
            {
                "detail": "Transfers are disabled as the warehouse is being maintained. Please try again later."
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    if not request.user.groups.filter(name="shop_users").exists():
        logger.debug("Permission denied: user is not in shop_users group.")
        return Response(
            {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
        )
    sku = request.data.get("sku")
    # Accept the quantity as either a string or a JSON number.
    try:
        transfer_quantity = int(str(request.data.get("transfer_quantity")))
    except (TypeError, ValueError):
        logger.debug("Invalid transfer quantity: not an integer.")
        return Response(
            {"detail": "Transfer quantity must be an integer."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if transfer_quantity <= 0:
        logger.debug("Invalid transfer quantity: less than or equal to zero.")
        return Response(
            {"detail": "Transfer quantity must be greater than zero."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        item = Item.objects.get(sku=sku)
        transfer_to_shop(item, request.user, transfer_quantity)
    except Item.DoesNotExist:
        logger.debug("Item not found: sku=%s", sku)
        return Response({"detail": "Item not found."}, status=status.HTTP_404_NOT_FOUND)
    except (ValueError, LookupError) as e:
        # Intentional, user-facing business-rule messages.
        logger.debug("Transfer rejected: %s", str(e))
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        # Do not leak unexpected internal error detail to the client.
        logger.error("Unexpected error during transfer.", exc_info=True)
        return Response(
            {"detail": "An unexpected error occurred while processing the transfer."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response({"detail": "Transfer successful."}, status=status.HTTP_200_OK)


def transfer_to_shop(
    item, shop_user, transfer_quantity, complete=False, cancel=False, manager=False
):
    if Admin.is_edit_locked() and not manager:
        raise ValueError(
            "Transfers are disabled as the warehouse is being maintained. Please try again later."
        )
    if cancel:
        transfer_item = TransferItem.objects.get(
            item=item, shop_user=shop_user
        ).delete()
    else:
        transfer_quantity = int(transfer_quantity)
        if transfer_quantity <= 0:
            raise ValueError("Transfer quantity must be greater than zero.")
        if item.quantity < transfer_quantity:
            raise ValueError("Not enough stock to transfer")
        if not complete:
            xfer_item, created = TransferItem.objects.get_or_create(
                shop_user=shop_user, item=item
            )
            if xfer_item.ordered:
                raise LookupError(
                    "This item has already been ordered and is awaiting dispatch. Please contact the warehouse manager if you wish to amend your order."
                )
            xfer_item.quantity = transfer_quantity
            xfer_item.save()
        else:
            # Dispatch: move stock from the warehouse to the shop. The
            # warehouse decrement is a single conditional UPDATE, so two
            # concurrent dispatches cannot oversell (guards against a
            # check-then-update race).
            shop_user = User.objects.get(id=shop_user)
            with transaction.atomic():
                rows = Item.objects.filter(
                    pk=item.pk, quantity__gte=transfer_quantity
                ).update(quantity=F("quantity") - transfer_quantity)
                if not rows:
                    raise ValueError("Not enough stock to transfer")
                shop_item, _ = ShopItem.objects.get_or_create(
                    item=item, shop_user=shop_user
                )
                ShopItem.objects.filter(pk=shop_item.pk).update(
                    quantity=F("quantity") + transfer_quantity
                )
                TransferItem.objects.filter(item=item, shop_user=shop_user).delete()
            item.refresh_from_db()


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_transfer_request(request):
    try:
        if not Admin.is_edit_locked():
            queryset = TransferItem.objects.filter(
                shop_user=request.user.id, ordered=False
            )
            if queryset.exists():
                # send notification email
                SendEmail().compose(
                    records=list(
                        queryset.values(
                            "id",
                            "item__sku",
                            "item__description",
                            "item__retail_price",
                            "quantity",
                        )
                    ),
                    user=request.user,
                    notification_type=SendEmail.EmailType.STOCK_TRANSFER,
                )
                # update records ordered status to True
                queryset.update(ordered=True)
            else:
                return Response(
                    {"detail": "There were no outstanding items to request!"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            return Response(
                {
                    "detail": "Transfers cannot proceed while the warehouse is under maintenance. Please try again later."
                },
                status=status.HTTP_403_FORBIDDEN,
            )
    except Exception:
        # Do not leak unexpected internal error detail to the client.
        logger.error("Unexpected error while submitting transfer.", exc_info=True)
        return Response(
            {"detail": "An unexpected error occurred while submitting the transfer request."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    audit.record(
        user=request.user,
        action=AuditEvent.TRANSFER_SENT,
        entity="transfer",
        description=request.user.get_username(),
    )
    return Response(
        {"detail": "Transfer successfully submitted."}, status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def complete_transfer(request):
    sku = request.data.get("sku")
    quantity = request.data.get("quantity")
    shop_user_id = request.data.get("shop_user_id")
    cancel = True if request.data.get("cancel") == "true" else False
    try:
        shop_user = User.objects.get(username=shop_user_id)
        shop_user_id = shop_user.id
    except User.DoesNotExist:
        logger.debug("User does not exist!")
        return Response(
            {"detail": "Shop user not found."}, status=status.HTTP_400_BAD_REQUEST
        )
    is_manager = is_warehouse_manager(request.user)
    if not is_manager:
        # Non-managers may only cancel, and only their own transfers. The
        # shop_user_id in the request body must not let one shop user act on
        # another's pending transfers.
        if not cancel:
            return Response(
                {"detail": "Permission denied. User is not in managers group."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if shop_user != request.user:
            return Response(
                {"detail": "Permission denied. You may only cancel your own transfers."},
                status=status.HTTP_403_FORBIDDEN,
            )
    if not cancel:
        # Dispatch requires a valid positive quantity; a negative value would
        # otherwise inflate warehouse stock.
        try:
            quantity = int(str(quantity))
        except (TypeError, ValueError):
            return Response(
                {"detail": "Quantity must be a positive integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if quantity <= 0:
            return Response(
                {"detail": "Quantity must be a positive integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    try:
        item = Item.objects.get(sku=sku)
        transfer_to_shop(
            manager=is_manager,
            item=item,
            shop_user=shop_user_id,
            transfer_quantity=quantity,
            complete=True,
            cancel=cancel,
        )
    except Item.DoesNotExist:
        logger.debug("Item not found: sku=%s", sku)
        return Response({"detail": "Item not found."}, status=status.HTTP_404_NOT_FOUND)
    except (ValueError, LookupError) as e:
        # Intentional, user-facing business-rule messages.
        logger.debug("Transfer action rejected: %s", str(e))
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        # Do not leak unexpected internal error detail to the client.
        logger.error("Unexpected error during transfer action.", exc_info=True)
        return Response(
            {"detail": "An unexpected error occurred while processing the transfer action."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    audit.record(
        user=request.user,
        action=AuditEvent.TRANSFER_COMPLETED,
        entity="transfer",
        description=request.user.get_username(),
    )
    return Response(
        {"detail": "Transfer action successful."}, status=status.HTTP_200_OK
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def app_config(request):
    config = Admin.objects.first()
    release = AppRelease.latest()
    return Response({
        "records_per_page": config.records_per_page if config else 25,
        "allow_upload_deletions": config.allow_upload_deletions if config else False,
        # The newest published build, so the app can offer its own update.
        "latest_app_version": release.version if release else None,
        "app_download_url": release.download_url if release else None,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_data_excel(request):
    """
    Export data as Excel for download.
    """
    if not (
        is_warehouse_manager(request.user)
        or request.user.groups.filter(name="shop_users").exists()
    ):
        logger.debug("Permission denied: user is not in shop_users or managers group.")
        return Response(
            {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
        )
    audit.record(
        user=request.user,
        action=AuditEvent.DATA_EXPORTED,
        entity="spreadsheet",
        description=request.user.get_username(),
    )
    return SpreadsheetTools(request).generate_excel_response()


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_data_excel(request):
    """
    Import data from an uploaded Excel file.
    """
    # Only allow managers to perform the upload.
    if not is_warehouse_manager(request.user):
        logger.debug("Permission denied: user is not in managers group.")
        return Response(
            {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
        )
    if not Admin.is_allow_updoads():
        logger.debug("Attempted upload when disabled.")
        return Response(
            {"detail": "Uploads are disabled in the app configuration."}, status=400
        )
    response = SpreadsheetTools(request).handle_excel_upload()
    if getattr(response, "status_code", 500) < 400:
        audit.record(
            user=request.user,
            action=AuditEvent.DATA_IMPORTED,
            entity="spreadsheet",
            description=request.user.get_username(),
        )
    return response


# ---------------------------------------------------------------------------
# Goods receipts (stock in, against a supplier purchase order) and item labels
# ---------------------------------------------------------------------------


def _parse_receipt_lines(raw_lines):
    """Normalise the submitted receipt lines into ``[(sku, quantity, description)]``.

    A repeated SKU in one delivery is summed, so the same item cannot be booked
    twice from a double click.
    """
    merged = {}
    for raw in raw_lines:
        if not isinstance(raw, dict):
            raise ValueError(_("Each receipt line must be an item and a quantity."))
        sku = str(raw.get("sku") or "").strip()
        if not sku:
            continue
        try:
            quantity = int(str(raw.get("quantity")))
        except (TypeError, ValueError):
            raise ValueError(_("The received quantity must be a whole number."))
        if quantity <= 0:
            raise ValueError(_("The received quantity must be greater than zero."))
        description = str(raw.get("description") or "").strip()
        if sku in merged:
            merged[sku] = (merged[sku][0] + quantity, merged[sku][1] or description)
        else:
            merged[sku] = (quantity, description)
    if not merged:
        raise ValueError(_("Add at least one item to receive."))
    return [(sku, qty, desc) for sku, (qty, desc) in merged.items()]


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def receive_from_supplier(request):
    """Book a supplier delivery: stock in against a PO number."""
    if Admin.is_edit_locked():
        return Response(
            {"detail": _("Receiving is disabled while the warehouse is being maintained.")},
            status=status.HTTP_403_FORBIDDEN,
        )

    po_number = str(request.data.get("po_number") or "").strip()
    if not po_number:
        return Response(
            {"detail": _("Enter the purchase order number.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        lines = _parse_receipt_lines(request.data.get("lines") or [])
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    supplier = str(request.data.get("supplier") or "").strip()
    notes = str(request.data.get("notes") or "").strip()

    try:
        with transaction.atomic():
            receipt = GoodsReceipt.objects.create(
                po_number=po_number,
                supplier=supplier,
                notes=notes,
                received_by=request.user if request.user.is_authenticated else None,
            )
            booked = []
            for sku, quantity, description in lines:
                item, created = Item.objects.get_or_create(
                    sku=sku,
                    defaults={
                        "description": description or sku,
                        "retail_price": Decimal("0.00"),
                        "quantity": 0,
                    },
                )
                if created and not description:
                    item.description = sku
                Item.objects.filter(pk=item.pk).update(
                    quantity=F("quantity") + quantity
                )
                item.refresh_from_db()
                GoodsReceiptLine.objects.create(
                    receipt=receipt,
                    item=item,
                    sku=sku,
                    description=description or item.description,
                    quantity=quantity,
                    unit=item.unit,
                )
                booked.append(
                    {
                        "sku": sku,
                        "description": description or item.description,
                        "quantity": quantity,
                        "warehouse_quantity": item.quantity,
                        "created_item": created,
                    }
                )
    except Exception:
        logger.error("Unexpected error while receiving a delivery.", exc_info=True)
        return Response(
            {"detail": _("An unexpected error occurred while receiving the delivery.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "id": receipt.id,
            "po_number": receipt.po_number,
            "supplier": receipt.supplier,
            "received_at": receipt.received_at,
            "received_by": request.user.username,
            "lines": booked,
            "total_quantity": sum(line["quantity"] for line in booked),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_receipts(request):
    """Recent goods receipts, newest first, with their lines."""
    try:
        limit = min(max(int(request.query_params.get("limit", 25)), 1), 200)
    except (TypeError, ValueError):
        limit = 25

    queryset = GoodsReceipt.objects.prefetch_related("lines").all()
    po_number = (request.query_params.get("po") or "").strip()
    if po_number:
        queryset = queryset.filter(po_number__icontains=po_number)

    rows = []
    for receipt in queryset[:limit]:
        rows.append(
            {
                "id": receipt.id,
                "po_number": receipt.po_number,
                "supplier": receipt.supplier,
                "received_at": receipt.received_at,
                "received_by": receipt.received_by.username
                if receipt.received_by
                else "",
                "notes": receipt.notes,
                "total_quantity": receipt.total_quantity,
                "lines": [
                    {
                        "sku": line.sku,
                        "description": line.description,
                        "quantity": line.quantity,
                    }
                    for line in receipt.lines.all()
                ],
            }
        )
    return Response({"results": rows, "count": len(rows)})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_sites(request):
    """The construction sites stock can be issued to (they are user accounts)."""
    return Response({"results": _site_accounts()})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def item_barcode(request, sku):
    """The Code 128 barcode for one item, as a standalone SVG document."""
    try:
        svg = render_barcode_svg(sku)
    except BarcodeError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    response = HttpResponse(svg, content_type="image/svg+xml")
    response["Cache-Control"] = "private, max-age=86400"
    return response


@login_required
def print_labels(request):
    """Printable label sheet: one barcode per item, ``copies`` labels each."""
    raw = request.GET.get("skus") or request.GET.get("sku") or ""
    skus = [value.strip() for value in raw.split(",") if value.strip()]
    try:
        copies = min(max(int(request.GET.get("copies", 1)), 1), 60)
    except (TypeError, ValueError):
        copies = 1

    items, errors = [], []
    if skus:
        found = {item.sku: item for item in Item.objects.filter(sku__in=skus)}
        for sku in skus:
            item = found.get(sku)
            if item is None:
                errors.append(_("Item %(sku)s was not found.") % {"sku": sku})
                continue
            try:
                svg = render_barcode_svg(item.sku)
            except BarcodeError as exc:
                errors.append(f"{sku}: {exc}")
                continue
            items.append({"item": item, "svg": svg})

    return render(
        request,
        "labels.html",
        {"items": items, "copies": copies, "copies_range": range(copies), "errors": errors},
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def issue_to_site(request):
    """Move stock from the warehouse to a construction site in one step."""
    if Admin.is_edit_locked():
        return Response(
            {"detail": _("Issuing stock is disabled while the warehouse is being maintained.")},
            status=status.HTTP_403_FORBIDDEN,
        )
    if not is_warehouse_manager(request.user):
        return Response(
            {"detail": _("Only a warehouse manager can issue stock to a site.")},
            status=status.HTTP_403_FORBIDDEN,
        )

    sku = str(request.data.get("sku") or "").strip()
    site_id = request.data.get("site_id")
    try:
        quantity = int(str(request.data.get("quantity")))
    except (TypeError, ValueError):
        return Response(
            {"detail": _("The issued quantity must be a whole number.")},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if quantity <= 0:
        return Response(
            {"detail": _("The issued quantity must be greater than zero.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        item = Item.objects.get(sku=sku)
    except Item.DoesNotExist:
        return Response({"detail": _("Item not found.")}, status=status.HTTP_404_NOT_FOUND)

    site = User.objects.filter(id=site_id, groups__name="shop_users").first()
    if site is None:
        return Response(
            {"detail": _("Site not found.")}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        transfer_to_shop(
            item=item,
            shop_user=site.id,
            transfer_quantity=quantity,
            complete=True,
            manager=True,
        )
    except (ValueError, LookupError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.error("Unexpected error while issuing to a site.", exc_info=True)
        return Response(
            {"detail": _("An unexpected error occurred while issuing the stock.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    item.refresh_from_db()
    return Response(
        {
            "detail": _("Stock issued to the site."),
            "sku": item.sku,
            "site": site.username,
            "warehouse_quantity": item.quantity,
        }
    )


# ---------------------------------------------------------------------------
# Stock documents: separate pages for adding, issuing, the warehouse and the
# issues report. A document is the audit record of a movement; the movement
# itself is applied once, and only after approval.
# ---------------------------------------------------------------------------

RECENT_DOCUMENTS = 25


def _form_lines(request):
    """Read the repeated sku/quantity inputs of a document form."""
    skus = request.POST.getlist("sku")
    quantities = request.POST.getlist("quantity")
    descriptions = request.POST.getlist("description")
    units = request.POST.getlist("unit")
    return [
        {
            "sku": sku,
            "quantity": quantity,
            "description": descriptions[index] if index < len(descriptions) else "",
            "unit": units[index] if index < len(units) else "",
        }
        for index, (sku, quantity) in enumerate(zip(skus, quantities))
        if str(sku).strip()
    ]


def _document_from_form(request, doc_type, *, pending=None):
    site_id = request.POST.get("site") or None
    site = (
        User.objects.filter(id=site_id, groups__name="shop_users").first()
        if site_id
        else None
    )
    return stock_documents.create_document(
        doc_type=doc_type,
        lines=_form_lines(request),
        site=site,
        counterparty=request.POST.get("counterparty", ""),
        reference=request.POST.get("reference", ""),
        external_ref=request.POST.get("external_ref", ""),
        notes=request.POST.get("notes", ""),
        created_by=request.user,
        source=StockDocument.WEB,
        # Only a warehouse manager may move stock without approval.
        pending=not is_warehouse_manager(request.user) if pending is None else pending,
        # The same paper the phone records: the date on it, where the goods go
        # and who signed it. Typed on the web, these were previously lost.
        document_date=_form_date(request.POST.get("document_date")),
        location=request.POST.get("location", ""),
        engineer_name=request.POST.get("engineer_name", ""),
    )


def _form_date(raw):
    """The date on the voucher, or None when the form left it empty."""
    from datetime import date

    text = (raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


@ensure_csrf_cookie
@login_required
def stock_page(request):
    """The warehouse and site stock, on their own page."""
    site_rows = (
        ShopItem.objects.select_related("item", "shop_user")
        .filter(quantity__gt=0)
        .order_by("shop_user__username", Lower("item__sku"))[:300]
    )
    return render(
        request,
        "pages/stock.html",
        {
            "js_messages": js_messages(),
            "site_rows": site_rows,
            "total_items": Item.objects.filter(is_active=True).count(),
            "total_quantity": Item.objects.filter(is_active=True).aggregate(
                total=Sum("quantity")
            )["total"]
            or 0,
            "is_manager": is_warehouse_manager(request.user),
        },
    )


@ensure_csrf_cookie
@login_required
def receipts_page(request):
    """Additions: PO receipt, transfer in from another project, site return."""
    if request.method == "POST":
        doc_type = request.POST.get("doc_type", "")
        if doc_type not in StockDocument.IN_TYPES:
            messages.error(request, _("Choose the type of addition."))
            return HttpResponseRedirect("/receipts/")
        try:
            document = _document_from_form(request, doc_type)
        except stock_documents.DocumentError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect("/receipts/")
        _announce(request, document)
        return HttpResponseRedirect("/receipts/")

    return render(
        request,
        "pages/receipts.html",
        {
            "sites": _site_accounts(),
            "unit_options": stock_documents.COMMON_UNITS,
            "types": [
                (value, _(label))
                for value, label in StockDocument.TYPE_CHOICES
                if value in StockDocument.IN_TYPES
            ],
            "recent": StockDocument.objects.select_related("site", "created_by")
            .prefetch_related("lines")
            .filter(direction=StockDocument.IN)[:RECENT_DOCUMENTS],
            "pending": StockDocument.objects.select_related("site", "created_by")
            .prefetch_related("lines")
            .filter(status=StockDocument.PENDING, direction=StockDocument.IN),
            "pending_title": _("Additions waiting for approval"),
            "back_url": "/receipts/",
            "is_manager": is_warehouse_manager(request.user),
            "form_title": _("New addition"),
            "form_hint": _("Stock goes IN"),
            "submit_label": _("Save the addition"),
            "site_types": StockDocument.SITE_RETURN,
            "action_url": "/receipts/",
        },
    )


@ensure_csrf_cookie
@login_required
def issues_page(request):
    """Issues: to a site, to another project, or back to the supplier."""
    if request.method == "POST":
        doc_type = request.POST.get("doc_type", "")
        if doc_type not in StockDocument.OUT_TYPES:
            messages.error(request, _("Choose the type of issue."))
            return HttpResponseRedirect("/issues/")
        try:
            document = _document_from_form(request, doc_type)
        except stock_documents.DocumentError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect("/issues/")
        _announce(request, document)
        return HttpResponseRedirect("/issues/")

    return render(
        request,
        "pages/issues.html",
        {
            "sites": _site_accounts(),
            "unit_options": stock_documents.COMMON_UNITS,
            "types": [
                (value, _(label))
                for value, label in StockDocument.TYPE_CHOICES
                if value in StockDocument.OUT_TYPES
            ],
            "pending": StockDocument.objects.select_related("site", "created_by")
            .prefetch_related("lines")
            .filter(status=StockDocument.PENDING, direction=StockDocument.OUT),
            "pending_title": _("Waiting for approval"),
            "back_url": "/issues/",
            "recent": StockDocument.objects.select_related(
                "site", "created_by", "decided_by"
            )
            .prefetch_related("lines")
            .filter(direction=StockDocument.OUT)[:RECENT_DOCUMENTS],
            "is_manager": is_warehouse_manager(request.user),
            "form_title": _("New issue"),
            "form_hint": _("Stock goes OUT"),
            "submit_label": _("Save the issue"),
            "site_types": "site_issue,site_return",
            "action_url": "/issues/",
        },
    )


@require_POST
@login_required
def decide_document(request, pk, action):
    """Approve or reject a pending document. Managers only."""
    if not is_warehouse_manager(request.user):
        messages.error(request, _("Only a warehouse manager can approve documents."))
        return HttpResponseRedirect(request.POST.get("next") or "/issues/")
    document = StockDocument.objects.filter(pk=pk).first()
    if document is None:
        messages.error(request, _("Document not found."))
        return HttpResponseRedirect(request.POST.get("next") or "/issues/")
    note = request.POST.get("note", "")
    try:
        if action == "approve":
            stock_documents.approve_document(document, user=request.user, note=note)
            messages.success(
                request,
                _("Document %(number)s approved and the stock was moved.") % {
                    "number": document.number
                },
            )
        elif action == "reject":
            stock_documents.reject_document(document, user=request.user, note=note)
            messages.success(
                request,
                _("Document %(number)s rejected; nothing was moved.") % {
                    "number": document.number
                },
            )
        else:
            messages.error(request, _("Unknown action."))
    except stock_documents.DocumentError as exc:
        messages.error(request, str(exc))
    return HttpResponseRedirect(request.POST.get("next") or "/issues/")




@login_required
def document_detail(request, pk):
    """The paper behind a document: what the site wrote, and what it moved.

    A manager deciding on a document needs the voucher itself — the date on it,
    where the goods go, who signed it and the photograph — not just a list of
    quantities. Everything the phone sent is shown here, and approve/reject post
    to the same view the lists use, so there is one decision path.
    """
    document = (
        StockDocument.objects.select_related("site", "created_by", "decided_by")
        .prefetch_related("lines")
        .filter(pk=pk)
        .first()
    )
    if document is None:
        messages.error(request, _("Document not found."))
        return HttpResponseRedirect("/issues/")
    return render(
        request,
        "pages/document_detail.html",
        {
            "document": document,
            "lines": document.lines.select_related("item").all(),
            "has_photo": bool(document.photo),
            "is_manager": is_warehouse_manager(request.user),
            "back_url": request.GET.get("next")
            or ("/receipts/" if document.direction == StockDocument.IN else "/issues/"),
        },
    )


@login_required
def document_photo(request, pk):
    """The photographed voucher, straight from the database.

    Not a file under MEDIA_ROOT: Render wipes the disk on every deploy, so a
    stored path becomes a broken image within a week.
    """
    document = StockDocument.objects.filter(pk=pk).only("photo", "photo_type").first()
    if document is None or not document.photo:
        raise Http404("No photo")
    response = HttpResponse(bytes(document.photo), content_type=document.photo_type or "image/jpeg")
    response["Cache-Control"] = "private, max-age=3600"
    return response



def _announce(request, document):
    """Tell the operator exactly what happened to their document."""
    if document.status == StockDocument.PENDING:
        messages.warning(
            request,
            _("Document %(number)s was saved and is waiting for a warehouse manager to approve it.")
            % {"number": document.number},
        )
    else:
        messages.success(
            request,
            _("Document %(number)s was saved and the stock was moved.") % {
                "number": document.number
            },
        )


@ensure_csrf_cookie
@login_required
def issues_report_page(request):
    """Everything that was issued in a date range, with an Excel export."""
    date_from, date_to = issue_report.parse_range(
        request.GET.get("from"), request.GET.get("to")
    )
    report = issue_report.build_report(date_from, date_to)

    if request.GET.get("export") == "xlsx":
        response = HttpResponse(
            issue_report.workbook_bytes(report),
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            f'attachment; filename="issues-{date_from}-to-{date_to}.xlsx"'
        )
        return response

    return render(
        request,
        "pages/issue_report.html",
        {
            "report": report,
            "date_from": date_from,
            "date_to": date_to,
            # The permits page returns here, so the operator keeps the window
            # they were reading instead of landing on a default one.
            "report_back": (
                f"/issues/report/?from={date_from:%Y-%m-%d}&to={date_to:%Y-%m-%d}"
            ),
        },
    )


PERMIT_BLANK_ROWS = 2


def _permits_context(document, *, is_manager, rows=None, assignments=None):
    """Everything the permits page shows, from the database or a failed save."""
    lines = list(document.lines.select_related("item").all())

    if rows is None:
        rows = [
            {
                "permit_no": permit.permit_no,
                "amount": permit.amount,
                "amount_display": company_permits.format_amount(permit.amount),
                "note": permit.note,
            }
            for permit in document.permits.all()
        ]
        assignments = {
            str(line.pk): line.permit.permit_no
            for line in lines
            if line.permit_id is not None
        }

    # Two blank rows are always offered so a second permit can be added without
    # a script; saving them offers the next pair.
    rows = list(rows) + [
        {"permit_no": "", "amount": "", "amount_display": "", "note": ""}
    ] * PERMIT_BLANK_ROWS

    return {
        "document": document,
        "rows": rows,
        "line_rows": [
            {
                "line": line,
                "value": company_permits.format_amount(
                    company_permits.line_value(line)
                ),
                "permit_no": assignments.get(str(line.pk), ""),
            }
            for line in lines
        ],
        "coverage": company_permits.coverage(document),
        "is_manager": is_manager,
    }


@login_required
def issue_permits_page(request, pk):
    """The company permits of one issue, and the items each one covers."""
    document = get_object_or_404(StockDocument, pk=pk)
    manager = is_warehouse_manager(request.user)
    self_url = f"/issues/{document.pk}/permits/"

    back = request.POST.get("next") or request.GET.get("next") or ""
    if not url_has_allowed_host_and_scheme(
        back, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        back = ""

    if request.method != "POST":
        return render(
            request,
            "pages/issue_permits.html",
            {
                **_permits_context(document, is_manager=manager),
                "back": back or "/issues/report/",
            },
        )

    if not manager:
        messages.error(
            request, _("Only a warehouse manager can record company permits.")
        )
        return HttpResponseRedirect(back or self_url)

    line_ids = {str(line.pk) for line in document.lines.all()}
    try:
        rows, assignments = company_permits.parse_form(request.POST, line_ids)
        company_permits.save_permits(document, rows, assignments, user=request.user)
    except company_permits.PermitError as exc:
        # Re-render what was typed: losing three permit numbers to a validation
        # error is how an operator stops using the page.
        context = _permits_context(
            document,
            is_manager=manager,
            rows=company_permits.submitted_rows(request.POST),
            assignments=company_permits.submitted_items(request.POST, line_ids),
        )
        context["back"] = back or "/issues/report/"
        messages.error(request, str(exc))
        return render(request, "pages/issue_permits.html", context)

    messages.success(
        request,
        _("Company permits recorded on %(number)s.") % {"number": document.number},
    )
    return HttpResponseRedirect(back or self_url)


RECONCILIATION_PAGE_SIZE = 100


def _reconciliation_redirect(request):
    """Back to the page with the filters the operator was reading."""
    target = request.POST.get("next") or "/reconciliation/"
    if not url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        target = "/reconciliation/"
    return HttpResponseRedirect(target)


@login_required
def reconciliation_page(request):
    """Everything that moved (or should have) without complete paperwork."""
    filters = reconciliation.parse_filters(request.GET)
    rows = reconciliation.build_rows(**filters)
    page = Paginator(rows, RECONCILIATION_PAGE_SIZE).get_page(request.GET.get("page"))

    query = request.GET.copy()
    query.pop("page", None)
    querystring = query.urlencode()
    # One place builds the three URLs, so none of them can grow a stray "?" or
    # lose the filters the operator is reading.
    suffix = f"?{querystring}" if querystring else ""
    page_prefix = f"/reconciliation/?{querystring}&" if querystring else "/reconciliation/?"

    return render(
        request,
        "pages/reconciliation.html",
        {
            "rows": page,
            "summary": reconciliation.summarize(rows),
            "reasons": reconciliation.REASON_LABELS,
            "short_reasons": reconciliation.SHORT_REASON_LABELS,
            "filters": filters,
            "sites": _site_accounts(),
            "next_url": f"/reconciliation/{suffix}",
            "export_url": f"/reconciliation/export/{suffix}",
            "page_url_prefix": page_prefix,
            "is_manager": is_warehouse_manager(request.user),
        },
    )


@login_required
@require_POST
def reconciliation_set_permit(request, pk):
    """Record the company voucher on a document, approving it when asked."""
    if not is_warehouse_manager(request.user):
        messages.error(
            request, _("Only a warehouse manager can complete the paperwork.")
        )
        return _reconciliation_redirect(request)

    document = get_object_or_404(StockDocument, pk=pk)
    try:
        reconciliation.record_permit(
            document,
            request.POST.get("external_ref"),
            approve=request.POST.get("approve") == "1",
            user=request.user,
        )
    except stock_documents.DocumentError as exc:
        messages.error(request, str(exc))
        return _reconciliation_redirect(request)

    messages.success(
        request,
        _("Voucher recorded on %(number)s.") % {"number": document.number},
    )
    return _reconciliation_redirect(request)


@login_required
@require_POST
def reconciliation_set_receipt_permit(request, pk):
    """Record the company voucher of a purchase-order delivery."""
    if not is_warehouse_manager(request.user):
        messages.error(
            request, _("Only a warehouse manager can complete the paperwork.")
        )
        return _reconciliation_redirect(request)

    receipt = get_object_or_404(GoodsReceipt, pk=pk)
    try:
        reconciliation.record_receipt_permit(
            receipt, request.POST.get("external_ref"), user=request.user
        )
    except stock_documents.DocumentError as exc:
        messages.error(request, str(exc))
        return _reconciliation_redirect(request)

    messages.success(
        request,
        _("Voucher recorded on the delivery of %(po)s.") % {"po": receipt.po_number},
    )
    return _reconciliation_redirect(request)


@login_required
def reconciliation_export(request):
    """The same list, as a spreadsheet."""
    rows = reconciliation.build_rows(**reconciliation.parse_filters(request.GET))
    response = HttpResponse(
        reconciliation.workbook_bytes(rows),
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = 'attachment; filename="missing-paperwork.xlsx"'
    return response


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def stock_documents_api(request):
    """The Android app's entry point: a submission that moves nothing yet."""
    if request.method == "POST":
        try:
            document = stock_documents.create_document(
                doc_type=str(request.data.get("doc_type") or ""),
                lines=request.data.get("lines") or [],
                site=User.objects.filter(
                    username=request.data.get("site") or "", groups__name="shop_users"
                ).first(),
                counterparty=request.data.get("counterparty", ""),
                reference=request.data.get("reference", ""),
                external_ref=request.data.get("external_ref", ""),
                notes=request.data.get("notes", ""),
                created_by=request.user,
                source=str(request.data.get("source") or StockDocument.MOBILE),
                pending=not is_warehouse_manager(request.user),
            )
        except stock_documents.DocumentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_serialize_document(document), status=status.HTTP_201_CREATED)

    queryset = StockDocument.objects.prefetch_related("lines")
    status_filter = request.query_params.get("status")
    if status_filter in dict(StockDocument.STATUS_CHOICES):
        queryset = queryset.filter(status=status_filter)
    return Response(
        {
            "results": [_serialize_document(document) for document in queryset[:100]],
            "count": queryset.count(),
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def decide_stock_document_api(request, pk):
    if not is_warehouse_manager(request.user):
        return Response(
            {"detail": _("Only a warehouse manager can approve documents.")},
            status=status.HTTP_403_FORBIDDEN,
        )
    document = StockDocument.objects.filter(pk=pk).first()
    if document is None:
        return Response({"detail": _("Document not found.")}, status=status.HTTP_404_NOT_FOUND)
    action = request.data.get("action")
    try:
        if action == "approve":
            document = stock_documents.approve_document(
                document, user=request.user, note=request.data.get("note", "")
            )
        elif action == "reject":
            document = stock_documents.reject_document(
                document, user=request.user, note=request.data.get("note", "")
            )
        else:
            return Response(
                {"detail": _("Unknown action.")}, status=status.HTTP_400_BAD_REQUEST
            )
    except stock_documents.DocumentError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(_serialize_document(document))


def _serialize_document(document):
    return {
        "id": document.id,
        "number": document.number,
        "direction": document.direction,
        "doc_type": document.doc_type,
        "status": document.status,
        "site": document.site.username if document.site_id else "",
        "counterparty": document.counterparty,
        "reference": document.reference,
        "external_ref": document.external_ref,
        "notes": document.notes,
        "created_by": document.created_by.username if document.created_by else "",
        "created_at": document.created_at,
        "applied_at": document.applied_at,
        "total_quantity": document.total_quantity,
        "lines": [
            {
                "sku": line.sku,
                "description": line.description,
                "quantity": line.quantity,
            }
            for line in document.lines.all()
        ],
    }


#: The sign-in page names the refusal — but only when the password was RIGHT.
#: A wrong password still gets the form's ordinary message, so the page never
#: tells an outsider which accounts exist or how they may sign in.
#: Each message is ONE literal: the translation collector reads source text, and
#: a string split over two lines produces a msgid nobody can match.
REFUSAL_MESSAGES = {
    REFUSAL_APP_ONLY: _lazy("This account signs in from the phone app only. Open the app, or ask a warehouse manager to allow web sign-in for it."),
    REFUSAL_INACTIVE: _lazy("This account is closed. Ask a warehouse manager to reopen it."),
}


class WarehouseLoginView(LoginView):
    """The ordinary sign-in form, plus the reason when the credentials were right."""

    def form_invalid(self, form):
        message = REFUSAL_MESSAGES.get(getattr(self.request, "login_refusal", None))
        if message:
            # The credentials were CORRECT, so "enter a correct username and
            # password" is simply untrue — it is replaced, not added to.
            form.errors.pop(NON_FIELD_ERRORS, None)
            form.add_error(None, message)
        return super().form_invalid(form)
