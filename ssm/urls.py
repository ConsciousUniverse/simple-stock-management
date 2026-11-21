from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.conf import settings
from django.views.generic import RedirectView

from ssm.health import healthz
from stock_manager.pages import AuditedPasswordChangeView
from stock_manager.views import switch_language

urlpatterns = [
    # Language switch (POST {"language": "ar", "next": "/"}).
    path("i18n/set-language/", switch_language, name="set_language"),
    # Public liveness probe (platform health check); never requires a session.
    path("healthz", healthz, name="healthz"),
]

if not getattr(settings, "ALLOW_PW_CHANGE", True):
    urlpatterns += [
        path("accounts/password_change/", RedirectView.as_view(url="/")),
        path("admin/password_change/", RedirectView.as_view(url="/admin/")),
        path("admin/password_change/done/", RedirectView.as_view(url="/admin/")),
    ]

urlpatterns += [
    path("", include("stock_manager.urls")),
    path("admin/", admin.site.urls),
    # The portal's own "password changed" confirmation, so the Django admin's
    # registration/password_change_done.html stays admin-styled.
    path(
        "accounts/password_change/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="registration/portal_password_change_done.html"
        ),
        name="password_change_done",
    ),
    # Matched before the include below, so a self-service password change is
    # recorded in the audit trail.
    path(
        "accounts/password_change/",
        AuditedPasswordChangeView.as_view(),
        name="password_change",
    ),
    path("accounts/", include("django.contrib.auth.urls")),
    path("api/auth/", include("rest_framework.urls")),
]
