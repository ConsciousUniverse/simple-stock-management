import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import Item, ShopItem, TransferItem, Admin
from .serializers import ItemSerializer, ShopItemSerializer, TransferItemSerializer
from .pagination import CustomPagination
from django.contrib.auth.models import User  # For accessing the User model
from rest_framework.response import (
    Response,
)  # For returning HTTP responses in REST framework
from rest_framework.decorators import api_view, permission_classes
from django.db.models.functions import Lower, Cast
from rest_framework import status
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db.models import IntegerField, Q
from email_service.email import SendEmail
from .utils import SpreadsheetTools
from natsort import natsorted

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
        ordering = self.request.query_params.get("ordering", None)
        if ordering:
            if ordering.lstrip('-') == "sku":
                items = list(queryset)
                reverse = ordering.startswith('-')
                items = natsorted(items, key=lambda x: x.sku, reverse=reverse)
                return items
            if ordering.startswith("-"):
                field = ordering[1:]
                if field == "quantity":
                    queryset = queryset.order_by(Cast(field, IntegerField()).desc())
                else:
                    queryset = queryset.order_by(Lower(field)).reverse()
            else:
                if ordering == "quantity":
                    queryset = queryset.order_by(Cast(ordering, IntegerField()))
                else:
                    queryset = queryset.order_by(Lower(ordering))
        else:
            queryset = queryset.order_by("last_updated").reverse()
        return queryset

    def create(self, request, *args, **kwargs):
        if not request.user.groups.filter(name="managers").exists():
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
                        return Response(serializer.data, status=status.HTTP_200_OK)
                    else:
                        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                else:
                    return Response({"detail": "Item with this SKU already exists."}, status=status.HTTP_400_BAD_REQUEST)
            except Item.DoesNotExist:
                pass
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not request.user.groups.filter(name="managers").exists():
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
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        if not request.user.groups.filter(name="managers").exists():
            return Response(
                {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
            )
        sku = kwargs.get("sku")
        try:
            item = Item.objects.get(sku=sku)
            item.is_active = False
            item.save()
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
        ordering = self.request.query_params.get("ordering", None)
        if ordering:
            if ordering.lstrip('-') == "sku":
                items = list(queryset)
                reverse = ordering.startswith('-')
                items = natsorted(items, key=lambda x: x.item.sku if x.item else '', reverse=reverse)
                return items
            if ordering.startswith("-"):
                field = ordering[1:]
                if field == "quantity":
                    queryset = queryset.order_by(Cast(field, IntegerField()).desc())
                else:
                    queryset = queryset.order_by(Lower(field)).reverse()
            else:
                if ordering == "quantity":
                    queryset = queryset.order_by(Cast(ordering, IntegerField()))
                else:
                    queryset = queryset.order_by(Lower(ordering))
        else:
            # Deterministic default ordering keeps pagination stable.
            queryset = queryset.order_by("-last_updated")
        return queryset


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
        if user.groups.filter(name="managers").exists():
            queryset = TransferItem.objects.filter(ordered=True)
        else:
            queryset = TransferItem.objects.filter(shop_user=user)
        search_query = self.request.query_params.get("search", None)
        if search_query:
            queryset = queryset.filter(
                Q(item__description__icontains=search_query)
                | Q(item__sku__icontains=search_query)
            )  # 🔍 Search filter
        ordering = self.request.query_params.get("ordering", None)
        if ordering:
            if ordering.lstrip('-') == "sku":
                items = list(queryset)
                reverse = ordering.startswith('-')
                items = natsorted(items, key=lambda x: x.item.sku, reverse=reverse)
                return items
            if ordering.startswith("-"):
                field = ordering[1:]
                if field == "quantity":
                    queryset = queryset.order_by(Cast(field, IntegerField()).desc())
                else:
                    queryset = queryset.order_by(Lower(field)).reverse()
            else:
                if ordering == "quantity":
                    queryset = queryset.order_by(Cast(ordering, IntegerField()))
                else:
                    queryset = queryset.order_by(Lower(ordering))
        else:
            # Deterministic default ordering keeps pagination stable.
            queryset = queryset.order_by("-last_updated")
        return queryset


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_edit_lock_status(request):
    if not request.user.groups.filter(name="managers").exists():
        return Response(
            {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
        )

    edit_lock_status = request.data.get("edit_lock_status", False)
    admin, created = Admin.objects.get_or_create(id=1)
    admin.edit_lock = edit_lock_status
    admin.save()
    return Response(
        {"edit_lock": admin.edit_lock},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_edit_lock_status(request):
    return Response({"edit_lock": Admin.is_edit_locked()})


# Main Page View
@ensure_csrf_cookie
@login_required
def index(request):
    return render(request, "index.html")


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
            if item.quantity < int(transfer_quantity):
                raise ValueError("Not enough stock to transfer")
            # transfer to ShopItem database
            shop_user = User.objects.get(id=shop_user)
            shop_item, created = ShopItem.objects.get_or_create(
                item=item, shop_user=shop_user
            )
            shop_item.quantity += transfer_quantity
            shop_item.save()
            # change quantity recorded for stock Item in warehouse
            item.quantity -= transfer_quantity
            item.save()
            # delete item from pending transfer
            TransferItem.objects.get(item=item, shop_user=shop_user).delete()


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
    is_manager = request.user.groups.filter(name="managers").exists()
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
    return Response(
        {"detail": "Transfer action successful."}, status=status.HTTP_200_OK
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def app_config(request):
    config = Admin.objects.first()
    return Response({
        "records_per_page": config.records_per_page if config else 25,
        "allow_upload_deletions": config.allow_upload_deletions if config else False,
        # Add other config values here if needed
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_data_excel(request):
    """
    Export data as Excel for download.
    """
    if not (
        request.user.groups.filter(name="managers").exists()
        or request.user.groups.filter(name="shop_users").exists()
    ):
        logger.debug("Permission denied: user is not in shop_users or managers group.")
        return Response(
            {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
        )
    return SpreadsheetTools(request).generate_excel_response()


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_data_excel(request):
    """
    Import data from an uploaded Excel file.
    """
    # Only allow managers to perform the upload.
    if not request.user.groups.filter(name="managers").exists():
        logger.debug("Permission denied: user is not in managers group.")
        return Response(
            {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
        )
    if not Admin.is_allow_updoads():
        logger.debug("Attempted upload when disabled.")
        return Response(
            {"detail": "Uploads are disabled in the app configuration."}, status=400
        )
    return SpreadsheetTools(request).handle_excel_upload()
