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
    stock_page,
    receipts_page,
    issues_page,
    decide_document,
    document_detail,
    document_photo,
    issues_report_page,
    issue_permits_page,
    reconciliation_page,
    reconciliation_set_permit,
    reconciliation_set_receipt_permit,
    reconciliation_export,
    stock_documents_api,
    decide_stock_document_api,
)
from stock_manager.pages import (
    android_page,
    audit_page,
    item_groups_page,
    labels_page,
    users_page,
)
from stock_manager import mobile_api
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
    # Registered before the router: its lookup regex is `.+` and would
    # otherwise swallow these sub-paths as an item detail.
    path("api/documents/", stock_documents_api, name="stock_documents_api"),
    path(
        "api/documents/<int:pk>/decide/",
        decide_stock_document_api,
        name="decide_stock_document_api",
    ),
    path("api/", include(router.urls)),
    # The page scripts read the reader's groups from here; it lives under /api/
    # like every other endpoint the browser calls.
    path("api/auth/user/", get_user, name="get_user"),
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
    # The picker; with ?skus= it renders the printable sheet instead.
    path("labels/", labels_page, name="print_labels"),
    # Our own code over several Oracle codes: read it, merge, and move.
    path("items/groups/", item_groups_page, name="item_groups_page"),
    path("users/", users_page, name="users_page"),
    path("android/", android_page, name="android_page"),
    # The Android app's API. `version/` is public on purpose: the app asks
    # before it has signed in, and a build that cannot check for an update is
    # exactly the build that never gets replaced.
    path("api/mobile/version/", mobile_api.VersionView.as_view(), name="mobile_version"),
    path("api/mobile/login/", mobile_api.LoginView.as_view(), name="mobile_login"),
    path("api/mobile/logout/", mobile_api.LogoutView.as_view(), name="mobile_logout"),
    path("api/mobile/me/", mobile_api.MeView.as_view(), name="mobile_me"),
    path(
        "api/mobile/phone-change-requests/",
        mobile_api.PhoneChangeRequestView.as_view(),
        name="mobile_phone_change_request",
    ),
    # The warehouse flow on the phone: a scanned label, then the signed voucher
    # with its items. Nothing moves until a manager approves it on the web.
    path(
        "api/mobile/items/lookup/",
        mobile_api.ItemLookupView.as_view(),
        name="mobile_item_lookup",
    ),
    path(
        "api/mobile/documents/",
        mobile_api.DocumentsView.as_view(),
        name="mobile_documents",
    ),
    path("audit/", audit_page, name="audit_page"),
    # One page per job: the warehouse, additions, issues, and the issues report.
    path("stock/", stock_page, name="stock_page"),
    path("receipts/", receipts_page, name="receipts_page"),
    path("issues/", issues_page, name="issues_page"),
    path("issues/report/", issues_report_page, name="issues_report"),
    path("issues/<int:pk>/permits/", issue_permits_page, name="issue_permits"),
    path("reconciliation/", reconciliation_page, name="reconciliation_page"),
    path(
        "reconciliation/<int:pk>/permit",
        reconciliation_set_permit,
        name="reconciliation_set_permit",
    ),
    path(
        "reconciliation/receipts/<int:pk>/permit",
        reconciliation_set_receipt_permit,
        name="reconciliation_set_receipt_permit",
    ),
    path(
        "reconciliation/export/",
        reconciliation_export,
        name="reconciliation_export",
    ),
    path("issues/<int:pk>/<str:action>/", decide_document, name="decide_document"),
    # The paper behind a document: header, lines and the photographed voucher.
    path("documents/<int:pk>/", document_detail, name="document_detail"),
    path(
        "documents/<int:pk>/photo/",
        document_photo,
        name="document_photo",
    ),
    path("api/issue/", issue_to_site, name="issue_to_site"),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
