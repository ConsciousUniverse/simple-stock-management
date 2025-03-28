from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import Item, ShopItem, TransferItem, Admin
from .serializers import ItemSerializer, ShopItemSerializer, TransferItemSerializer
from .pagination import CustomPagination
from django.contrib.auth.models import User  # For accessing the User model
from rest_framework.response import (
    Response,
)  # For returning HTTP responses in REST framework
from rest_framework.decorators import api_view
from django.db.models.functions import Lower
from rest_framework.decorators import permission_classes
from django.http import JsonResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
import logging
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.db.models import Q

logger = logging.getLogger(__name__)


# API View
class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
    lookup_field = "sku"
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        queryset = Item.objects.all()
        search_query = self.request.query_params.get("search", None)
        if search_query:
            queryset = queryset.filter(
                Q(description__icontains=search_query) | Q(sku__icontains=search_query)
            )  # 🔍 Search filter
        ordering = self.request.query_params.get("ordering", None)
        if ordering:
            if ordering.startswith("-"):
                queryset = queryset.order_by(Lower(ordering[1:])).reverse()
            else:
                queryset = queryset.order_by(Lower(ordering))
        else:
            queryset = queryset.order_by(Lower("sku"))
        return queryset

    def update(self, request, *args, **kwargs):
        if not request.user.groups.filter(name="managers").exists():
            return Response(
                {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not request.user.groups.filter(name="managers").exists():
            return Response(
                {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)


class ShopItemViewSet(viewsets.ModelViewSet):
    queryset = ShopItem.objects.all()
    serializer_class = ShopItemSerializer
    lookup_field = "item__sku"
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        queryset = ShopItem.objects.filter(shop_user=self.request.user)
        search_query = self.request.query_params.get("search", None)
        if search_query:
            queryset = queryset.filter(
                Q(item__description__icontains=search_query)
                | Q(item__sku__icontains=search_query)
            )  # 🔍 Search filter
        ordering = self.request.query_params.get("ordering", None)
        if ordering:
            if ordering.startswith("-"):
                queryset = queryset.order_by(Lower(ordering[1:])).reverse()
            else:
                queryset = queryset.order_by(Lower(ordering))
        else:
            queryset = queryset.order_by(Lower("item__sku"))
        return queryset


class TransferItemViewSet(viewsets.ModelViewSet):
    queryset = TransferItem.objects.all()
    serializer_class = TransferItemSerializer
    lookup_field = "item__sku"
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        user = self.request.user
        if user.groups.filter(name="managers").exists():
            queryset = TransferItem.objects.all()
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
            if ordering.startswith("-"):
                queryset = queryset.order_by(Lower(ordering[1:])).reverse()
            else:
                queryset = queryset.order_by(Lower(ordering))
        else:
            queryset = queryset.order_by(Lower("item__sku"))
        return queryset


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


@api_view(["POST", "PATCH"])
@permission_classes([IsAuthenticated])
def complete_transfer(request):
    sku = request.data.get("sku")
    quantity = request.data.get("quantity")
    shop_user_id = request.data.get("shop_user_id")
    cancel = True if request.data.get("cancel") == "true" else False
    if request.method == "PATCH":
        try:
            transfer_item = TransferItem.objects.get(item__sku=sku)
            transfer_item.quantity = quantity
            transfer_item.save()
        except Item.DoesNotExist:
            logger.debug("Item not found: sku=%s", sku)
            return Response(
                {"detail": "Item not found."}, status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as e:
            logger.debug("ValueError during transfer: %s", str(e))
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"detail": "Transfer action successful."}, status=status.HTTP_200_OK
        )
    else:
        if not request.user.groups.filter(name="managers").exists() and not cancel:
            return Response(
                {"detail": "Permission denied. User is not in managers group."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            item = Item.objects.get(sku=sku)
            item.transfer_to_shop(
                shop_user=shop_user_id,
                transfer_quantity=quantity,
                complete=True,
                cancel=cancel,
            )
        except Item.DoesNotExist:
            logger.debug("Item not found: sku=%s", sku)
            return Response(
                {"detail": "Item not found."}, status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as e:
            logger.debug("ValueError during transfer: %s", str(e))
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"detail": "Transfer action successful."}, status=status.HTTP_200_OK
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transfer_item(request):
    if Admin.objects.first().edit_lock:
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
    transfer_quantity = request.data.get("transfer_quantity")
    if not transfer_quantity.isdigit():
        logger.debug("Invalid transfer quantity: not an integer.")
        return Response(
            {"detail": "Transfer quantity must be an integer."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    transfer_quantity = int(transfer_quantity)
    if transfer_quantity <= 0:
        logger.debug("Invalid transfer quantity: less than or equal to zero.")
        return Response(
            {"detail": "Transfer quantity must be greater than zero."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        item = Item.objects.get(sku=sku)
        item.transfer_to_shop(request.user, transfer_quantity)
    except Item.DoesNotExist:
        logger.debug("Item not found: sku=%s", sku)
        return Response({"detail": "Item not found."}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as e:
        logger.debug("ValueError during transfer: %s", str(e))
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"detail": "Transfer successful."}, status=status.HTTP_200_OK)


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


@csrf_exempt
def get_edit_lock_status(request):
    if request.method == "GET":
        edit_lock = Admin.is_edit_locked()
        return JsonResponse({"edit_lock": edit_lock})
    return JsonResponse({"error": "Invalid request method"}, status=400)
