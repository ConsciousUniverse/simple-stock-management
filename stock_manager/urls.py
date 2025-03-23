from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ItemViewSet, ShopItemViewSet, TransferItemViewSet, index, get_user, transfer_item, complete_transfer, toggle_update_mode, get_edit_lock_status  # Add TransferItemViewSet import
from rest_framework.authtoken.views import obtain_auth_token
from django.conf.urls.static import static
from django.conf import settings

router = DefaultRouter()
router.register(r'items', ItemViewSet)
router.register(r'shop_items', ShopItemViewSet)
router.register(r'transfer_items', TransferItemViewSet)  # Add this line

urlpatterns = [
    path('', index, name='index'),
    path('api/', include(router.urls)),
    path('auth/user/', get_user, name='get_user'),  # Custom user endpoint
    path('auth/token/', obtain_auth_token, name='api_token_auth'),  # Optional token login
    path('api/transfer/', transfer_item, name='transfer_item'),  # Add this line
    path('api/complete-transfer/', complete_transfer, name='complete_transfer'),
    path('api/toggle_update_mode/', toggle_update_mode, name='toggle_update_mode'),  # Ensure correct import
    path('api/get_edit_lock_status/', get_edit_lock_status, name='get_edit_lock_status'),  # Add this line
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)