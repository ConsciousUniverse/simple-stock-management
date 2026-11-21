"""The audit trail: who did what.

The value of this log is that it cannot be wrong about the things it claims:
it is written by the write paths themselves (not by a view counter), it keeps a
snapshot of the actor's name so a deleted user does not erase their history,
and a failure to write it never fails the action that was already taken.
"""

import pytest
from django.contrib.auth.models import User

from stock_manager import audit
from stock_manager import documents as service
from stock_manager.models import AuditEvent, Item, StockDocument

pytestmark = pytest.mark.django_db


def events(action=None):
    queryset = AuditEvent.objects.all()
    if action:
        queryset = queryset.filter(action=action)
    return queryset


class TestAuthEvents:
    def test_a_sign_in_is_recorded_with_the_name(self, client, manager):
        response = client.post(
            "/accounts/login/", {"username": "manager", "password": "test-pass-123"}
        )
        assert response.status_code == 302

        event = events(AuditEvent.LOGIN).get()
        assert event.actor_name == "manager"
        assert event.actor_id == manager.pk

    def test_a_refused_sign_in_is_recorded_without_the_password(self, client, manager):
        client.post(
            "/accounts/login/", {"username": "manager", "password": "wrong-pass-999"}
        )

        event = events(AuditEvent.LOGIN_FAILED).get()
        assert event.entity_id == "manager"
        assert "wrong-pass-999" not in event.description
        assert event.actor is None

    def test_signing_out_is_recorded(self, client, manager):
        client.force_login(manager)
        client.post("/accounts/logout/")

        assert events(AuditEvent.LOGOUT).filter(actor_name="manager").exists()

    def test_a_self_service_password_change_is_recorded(self, client, manager):
        client.force_login(manager)
        response = client.post(
            "/accounts/password_change/",
            {
                "old_password": "test-pass-123",
                "new_password1": "a-new-pass-456",
                "new_password2": "a-new-pass-456",
            },
        )
        assert response.status_code == 302

        event = events(AuditEvent.PASSWORD_CHANGED).get()
        assert event.actor_name == "manager"
        # The new secret must never be written to the log.
        assert "a-new-pass-456" not in event.description


class TestStockEvents:
    def test_creating_a_document_records_its_number_and_lines(self, manager, make_item):
        make_item(sku="SKU-1", quantity=0)

        document = service.create_document(
            doc_type=StockDocument.PO_RECEIPT,
            lines=[{"sku": "SKU-1", "quantity": 4, "unit": "متر"}],
            counterparty="Elsewedy",
            created_by=manager,
        )

        event = events(AuditEvent.DOCUMENT_CREATED).get()
        assert event.actor_name == "manager"
        assert event.entity_id == str(document.pk)
        assert document.number in event.description
        assert "SKU-1 ×4 متر" in event.description
        assert "Elsewedy" in event.description

    def test_approving_a_pending_document_is_recorded(
        self, client, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=10)
        document = service.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 2}],
            site=shop_user,
            created_by=shop_user,
            pending=True,
        )

        client.force_login(manager)
        response = client.post(
            f"/issues/{document.pk}/approve/", {"note": "ok"}, follow=True
        )
        assert response.status_code == 200

        event = events(AuditEvent.DOCUMENT_APPROVED).get()
        assert event.actor_name == "manager"
        assert document.number in event.description

    def test_rejecting_a_pending_document_is_recorded_with_the_reason(
        self, client, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=10)
        document = service.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 2}],
            site=shop_user,
            created_by=shop_user,
            pending=True,
        )

        client.force_login(manager)
        client.post(f"/issues/{document.pk}/reject/", {"note": "الكمية كبيرة"})

        event = events(AuditEvent.DOCUMENT_REJECTED).get()
        assert "الكمية كبيرة" in event.description


class TestCatalogueEvents:
    def test_creating_an_item_through_the_api_is_recorded(
        self, manager_client, manager
    ):
        response = manager_client.post(
            "/api/items/",
            {
                "sku": "NEW-1",
                "description": "New widget",
                "retail_price": "5.00",
                "quantity": 0,
            },
        )
        assert response.status_code == 201

        event = events(AuditEvent.ITEM_CREATED).get()
        assert event.entity_id == "NEW-1"
        assert event.actor_name == "manager"

    def test_updating_an_item_records_which_fields_changed(
        self, manager_client, make_item
    ):
        make_item(sku="SKU-1", description="Old name")

        response = manager_client.patch(
            "/api/items/SKU-1/",
            {"sku": "SKU-1", "description": "New name"},
            format="json",
        )
        assert response.status_code == 200

        event = events(AuditEvent.ITEM_UPDATED).get()
        assert "description" in event.description

    def test_removing_an_item_is_recorded(self, manager_client, make_item):
        make_item(sku="SKU-1")

        response = manager_client.delete("/api/items/SKU-1/")
        assert response.status_code == 204

        event = events(AuditEvent.ITEM_DELETED).get()
        assert event.entity_id == "SKU-1"
        # The row survives for the documents that reference it.
        assert Item.objects.get(pk="SKU-1").is_active is False


class TestTheLogItself:
    def test_a_failed_write_does_not_break_the_action(
        self, client, manager, monkeypatch, make_item
    ):
        make_item(sku="SKU-1", quantity=0)

        def boom(*args, **kwargs):
            raise RuntimeError("the log table is unavailable")

        monkeypatch.setattr(AuditEvent.objects, "create", boom)

        response = client.post(
            "/accounts/login/", {"username": "manager", "password": "test-pass-123"}
        )

        # The sign-in succeeded even though nothing could be recorded.
        assert response.status_code == 302
        assert events(AuditEvent.LOGIN).count() == 0

    def test_the_actor_name_survives_deleting_the_user(self, manager, make_item):
        make_item(sku="SKU-1", quantity=0)
        service.create_document(
            doc_type=StockDocument.PO_RECEIPT,
            lines=[{"sku": "SKU-1", "quantity": 1}],
            counterparty="Elsewedy",
            created_by=manager,
        )

        manager.delete()

        event = events(AuditEvent.DOCUMENT_CREATED).get()
        assert event.actor is None
        assert event.actor_name == "manager"

    def test_the_manager_reads_the_log(self, client, manager):
        audit.record(user=manager, action=AuditEvent.LOGIN, description="manager")
        client.force_login(manager)

        response = client.get("/audit/")

        assert response.status_code == 200
        assert b"manager" in response.content
        assert response.context["total"] >= 1

    def test_a_site_user_is_sent_away(self, client, shop_user):
        client.force_login(shop_user)

        response = client.get("/audit/")

        assert response.status_code == 302
        assert response.headers["Location"] == "/"

    def test_the_area_filter_narrows_the_list(self, client, manager):
        audit.record(user=manager, action=AuditEvent.LOGIN, description="a sign-in")
        audit.record(
            user=manager,
            action=AuditEvent.ITEM_UPDATED,
            entity="item",
            entity_id="SKU-9",
            description="SKU-9 · description",
        )
        client.force_login(manager)

        response = client.get("/audit/?area=items")

        assert response.context["total"] == 1
        assert response.context["events"][0].action == AuditEvent.ITEM_UPDATED

    def test_the_search_matches_a_document_number(self, client, manager):
        audit.record(
            user=manager,
            action=AuditEvent.DOCUMENT_CREATED,
            description="RCV-2026-000042 · PO receipt",
        )
        audit.record(user=manager, action=AuditEvent.LOGIN, description="manager")
        client.force_login(manager)

        response = client.get("/audit/?q=RCV-2026-000042")

        assert response.context["total"] == 1

    def test_the_action_labels_are_translated(self, client, manager):
        audit.record(user=manager, action=AuditEvent.DOCUMENT_APPROVED)
        client.force_login(manager)

        # The locale middleware reads the cookie on every request, so the cookie
        # (not a translation.override) is what makes the page Arabic.
        client.cookies["django_language"] = "ar"
        response = client.get("/audit/")

        assert "اعتماد مستند" in response.content.decode()

    def test_the_log_never_stores_an_ip_address(self):
        # The project deliberately does not log client IPs (see AXES settings),
        # so the trail must not grow one field at a time.
        field_names = {field.name for field in AuditEvent._meta.get_fields()}
        assert not any("ip" == name or name.startswith("ip_") for name in field_names)
