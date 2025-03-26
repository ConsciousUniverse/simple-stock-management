from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.views.generic import RedirectView

urlpatterns = []

if not getattr(settings, "ALLOW_PW_CHANGE", True):
    urlpatterns += [
        path("accounts/password_change/", RedirectView.as_view(url="/")),
    ]

urlpatterns += [
    path("", include("stock_manager.urls")),
    path("admin/", admin.site.urls),
    path("api/", include("stock_manager.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("api/auth/", include("rest_framework.urls")),
]
