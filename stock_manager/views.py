from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import Item, ShopItem, Admin
from .serializers import ItemSerializer, ShopItemSerializer
from .pagination import CustomPagination
from django.contrib.auth.models import User  # For accessing the User model
from rest_framework.response import (
    Response,
)  # For returning HTTP responses in REST framework
from rest_framework.decorators import api_view
from django.db.models.functions import Lower
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
import logging

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
                description__icontains=search_query
            )  # 🔍 Search filter
        ordering = self.request.query_params.get("ordering", None)
        if ordering:
            if ordering.startswith('-'):
                queryset = queryset.order_by(Lower(ordering[1:])).reverse()
            else:
                queryset = queryset.order_by(Lower(ordering))
        else:
            queryset = queryset.order_by(Lower('sku'))
        return queryset

    def update(self, request, *args, **kwargs):
        if not request.user.groups.filter(name='managers').exists():
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not request.user.groups.filter(name='managers').exists():
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
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
                item__description__icontains=search_query
            )  # 🔍 Search filter
        ordering = self.request.query_params.get("ordering", None)
        if ordering:
            if ordering.startswith('-'):
                queryset = queryset.order_by(Lower(ordering[1:])).reverse()
            else:
                queryset = queryset.order_by(Lower(ordering))
        else:
            queryset = queryset.order_by(Lower('item__sku'))
        return queryset


# Main Page View
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
    if Admin.objects.first().edit_lock:
        logger.debug("Transfer attempt while update mode is enabled.")
        return Response({"detail": "Transfers are disabled in update mode."}, status=status.HTTP_403_FORBIDDEN)

    if not request.user.groups.filter(name='shop_users').exists():
        logger.debug("Permission denied: user is not in shop_users group.")
        return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

    if request.session.get('update_mode', False):
        logger.debug("Transfer attempt while update mode is enabled.")
        return Response({"detail": "Transfers are disabled in update mode."}, status=status.HTTP_403_FORBIDDEN)

    sku = request.data.get("sku")
    transfer_quantity = request.data.get("transfer_quantity")

    if not transfer_quantity.isdigit():
        logger.debug("Invalid transfer quantity: not an integer.")
        return Response({"detail": "Transfer quantity must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

    transfer_quantity = int(transfer_quantity)
    if transfer_quantity <= 0:
        logger.debug("Invalid transfer quantity: less than or equal to zero.")
        return Response({"detail": "Transfer quantity must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        item = Item.objects.get(sku=sku)
        item.transfer_to_shop(request.user, transfer_quantity)
    except Item.DoesNotExist:
        logger.debug("Item not found: sku=%s", sku)
        return Response({"detail": "Item not found."}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as e:
        logger.debug("ValueError during transfer: %s", str(e))
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    logger.debug("Transfer successful: sku=%s, quantity=%d", sku, transfer_quantity)
    return Response({"detail": "Transfer successful."}, status=status.HTTP_200_OK)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_update_mode(request):
    if not request.user.groups.filter(name='managers').exists():
        return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

    update_mode = request.data.get("update_mode", False)
    admin, created = Admin.objects.get_or_create(id=1)
    admin.edit_lock = update_mode
    admin.save()
    return Response({"detail": f"Update mode {'enabled' if update_mode else 'disabled'}."}, status=status.HTTP_200_OK)
