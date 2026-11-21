from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ItemViewSet,
    ShopItemViewSet,
    TransferItemViewSet,
    index,
    get_user,
    transfer_item,
    complete_transfer,
    set_edit_lock_status,
    get_edit_lock_status,
    submit_transfer_request,
    export_data_excel,
    import_data_excel,
    app_config,  # Add this import
    receive_from_supplier,
    list_receipts,
    list_sites,
    item_barcode,
    print_labels,
    issue_to_site,
)
from django.conf.urls.static import static
from django.conf import settings

from rest_framework import routers

class PathRouter(DefaultRouter):
    def get_lookup_regex(self, viewset, lookup_prefix=''):
        # Use path converter for detail routes
        lookup_field = getattr(viewset, 'lookup_field', 'pk')
        return r'(?P<%s>.+)' % (lookup_prefix + lookup_field)

# Use PathRouter instead of DefaultRouter
router = PathRouter()
router.register(r"items", ItemViewSet)
router.register(r"shop_items", ShopItemViewSet)
# "site" is the Orascom term for the same stock owner; keep both names working.
router.register(r"site_items", ShopItemViewSet, basename="site-items")
router.register(r"transfer_items", TransferItemViewSet)

urlpatterns = [
    path("", index, name="index"),
    # Must precede the router include: its lookup regex is `.+`, which would
    # otherwise match `api/items/<sku>/barcode.svg` as an item detail.
    path("api/items/<str:sku>/barcode.svg", item_barcode, name="item_barcode"),
    path("api/", include(router.urls)),
    path("auth/user/", get_user, name="get_user"),  # Custom user endpoint
    path("api/transfer/", transfer_item, name="transfer_item"),
    path(
        "api/submit-transfer-request/",
        submit_transfer_request,
        name="submit-transfer-request",
    ),
    path("api/complete-transfer/", complete_transfer, name="complete_transfer"),
    path(
        "api/set_edit_lock_status/", set_edit_lock_status, name="set_edit_lock_status"
    ),
    path(
        "api/get_edit_lock_status/", get_edit_lock_status, name="get_edit_lock_status"
    ),
    path("api/export_data/", export_data_excel, name="export_data_excel"),
    path("api/import_data/", import_data_excel, name="import_data_excel"),
    path("api/app_config/", app_config, name="app_config"),  # Register the endpoint
    # Goods receipts (stock in against a supplier PO) and item labels.
    path("api/receiving/", receive_from_supplier, name="receive_from_supplier"),
    path("api/receipts/", list_receipts, name="list_receipts"),
    path("api/sites/", list_sites, name="list_sites"),
    path("labels/", print_labels, name="print_labels"),
    path("api/issue/", issue_to_site, name="issue_to_site"),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
