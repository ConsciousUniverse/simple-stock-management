"""Stock documents: additions, issues, the approval gate and the dedup key.

The rules these tests protect are the ones an operator depends on for the
balances to stay correct:

* a manager's web entry moves the stock immediately,
* a site user's entry (the mobile app) moves NOTHING until a manager approves,
* the same company voucher can never move stock twice,
* an issue can never take more than the warehouse holds.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from stock_manager import documents as service
from stock_manager.models import Item, ShopItem, StockDocument

pytestmark = pytest.mark.django_db


def doc_type(value):
    return value


class TestAdditions:
    def test_a_po_receipt_creates_unknown_items_and_raises_stock(self, manager, make_item):
        make_item(sku="SKU-1", quantity=5)

        document = service.create_document(
            doc_type=StockDocument.PO_RECEIPT,
            lines=[
                {"sku": "SKU-1", "quantity": 7},
                {"sku": "SKU-NEW", "quantity": 3, "description": "New widget"},
            ],
            counterparty="Elsewedy",
            reference="PO-2026-000123",
            created_by=manager,
        )

        assert document.status == StockDocument.APPROVED
        assert document.applied_at is not None
        assert document.number.startswith("RCV-")
        assert Item.objects.get(pk="SKU-1").quantity == 12
        assert Item.objects.get(pk="SKU-NEW").quantity == 3
        assert Item.objects.get(pk="SKU-NEW").description == "New widget"

    def test_a_site_return_raises_the_warehouse_and_lowers_the_site(
        self, manager, make_item, shop_user
    ):
        item = make_item(sku="SKU-1", quantity=2)
        ShopItem.objects.create(shop_user=shop_user, item=item, quantity=4)

        service.create_document(
            doc_type=StockDocument.SITE_RETURN,
            lines=[{"sku": "SKU-1", "quantity": 3}],
            site=shop_user,
            created_by=manager,
        )

        assert Item.objects.get(pk="SKU-1").quantity == 5
        assert ShopItem.objects.get(shop_user=shop_user, item=item).quantity == 1

    def test_a_site_cannot_return_more_than_it_holds(self, manager, make_item, shop_user):
        item = make_item(sku="SKU-1", quantity=2)
        ShopItem.objects.create(shop_user=shop_user, item=item, quantity=1)

        with pytest.raises(service.DocumentError):
            service.create_document(
                doc_type=StockDocument.SITE_RETURN,
                lines=[{"sku": "SKU-1", "quantity": 3}],
                site=shop_user,
                created_by=manager,
            )

        assert Item.objects.get(pk="SKU-1").quantity == 2
        assert ShopItem.objects.get(shop_user=shop_user, item=item).quantity == 1
        assert not StockDocument.objects.exists()

    def test_a_transfer_in_needs_the_other_project(self, manager, make_item):
        make_item(sku="SKU-1")

        with pytest.raises(service.DocumentError):
            service.create_document(
                doc_type=StockDocument.PROJECT_TRANSFER_IN,
                lines=[{"sku": "SKU-1", "quantity": 1}],
                created_by=manager,
            )


class TestIssues:
    def test_issuing_to_a_site_moves_the_stock_both_ways(self, manager, make_item, shop_user):
        item = make_item(sku="SKU-1", quantity=10)

        document = service.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 4}],
            site=shop_user,
            created_by=manager,
        )

        assert document.number.startswith("ISS-")
        assert Item.objects.get(pk="SKU-1").quantity == 6
        assert ShopItem.objects.get(shop_user=shop_user, item=item).quantity == 4

    def test_transferring_to_another_project_leaves_the_site_stock_alone(
        self, manager, make_item, shop_user
    ):
        make_item(sku="SKU-1", quantity=10)

        service.create_document(
            doc_type=StockDocument.PROJECT_TRANSFER_OUT,
            lines=[{"sku": "SKU-1", "quantity": 5}],
            counterparty="New Capital site",
            created_by=manager,
        )

        assert Item.objects.get(pk="SKU-1").quantity == 5
        assert not ShopItem.objects.exists()

    def test_returning_goods_to_the_supplier_lowers_the_warehouse(
        self, manager, make_item
    ):
        make_item(sku="SKU-1", quantity=3)

        service.create_document(
            doc_type=StockDocument.SUPPLIER_RETURN,
            lines=[{"sku": "SKU-1", "quantity": 2}],
            counterparty="Elsewedy",
            created_by=manager,
        )

        assert Item.objects.get(pk="SKU-1").quantity == 1

    def test_an_issue_can_never_take_more_than_the_warehouse_holds(
        self, manager, make_item, shop_user
    ):
        make_item(sku="SKU-1", quantity=2)

        with pytest.raises(service.DocumentError):
            service.create_document(
                doc_type=StockDocument.SITE_ISSUE,
                lines=[{"sku": "SKU-1", "quantity": 3}],
                site=shop_user,
                created_by=manager,
            )

        assert Item.objects.get(pk="SKU-1").quantity == 2
        assert not StockDocument.objects.exists()

    def test_a_repeated_line_in_one_payload_is_summed_once(self, manager, make_item):
        make_item(sku="SKU-1", quantity=10)

        document = service.create_document(
            doc_type=StockDocument.PO_RECEIPT,
            lines=[
                {"sku": "SKU-1", "quantity": 2},
                {"sku": "SKU-1", "quantity": 3},
            ],
            counterparty="Elsewedy",
            created_by=manager,
        )

        assert Item.objects.get(pk="SKU-1").quantity == 15
        assert document.lines.count() == 1


class TestApprovalGate:
    def test_a_mobile_submission_moves_nothing_until_it_is_approved(
        self, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=10)

        document = service.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 4}],
            site=shop_user,
            created_by=shop_user,
            source=StockDocument.MOBILE,
        )

        assert document.status == StockDocument.PENDING
        assert document.applied_at is None
        assert Item.objects.get(pk="SKU-1").quantity == 10  # nothing moved

        service.approve_document(document, user=shop_user)
        document.refresh_from_db()

        assert document.status == StockDocument.APPROVED
        assert Item.objects.get(pk="SKU-1").quantity == 6

    def test_a_document_cannot_be_applied_twice(self, manager, make_item):
        make_item(sku="SKU-1", quantity=10)
        document = service.create_document(
            doc_type=StockDocument.PO_RECEIPT,
            lines=[{"sku": "SKU-1", "quantity": 1}],
            counterparty="Elsewedy",
            created_by=manager,
        )

        with pytest.raises(service.DocumentError):
            service.approve_document(document, user=manager)

        assert Item.objects.get(pk="SKU-1").quantity == 11

    def test_a_rejected_document_never_moves_and_cannot_be_approved(
        self, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=10)
        document = service.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 2}],
            site=shop_user,
            created_by=shop_user,
            source=StockDocument.MOBILE,
        )

        service.reject_document(document, user=shop_user, note="not authorised")
        document.refresh_from_db()

        assert document.status == StockDocument.REJECTED
        with pytest.raises(service.DocumentError):
            service.approve_document(document, user=shop_user)
        assert Item.objects.get(pk="SKU-1").quantity == 10


class TestVoucherDeduplication:
    def test_the_same_company_voucher_cannot_move_stock_twice(
        self, manager, make_item, shop_user
    ):
        make_item(sku="SKU-1", quantity=10)

        service.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 4}],
            site=shop_user,
            external_ref="VCH-2026-0042",
            created_by=manager,
        )
        with pytest.raises(service.DocumentError) as error:
            service.create_document(
                doc_type=StockDocument.SITE_ISSUE,
                lines=[{"sku": "SKU-1", "quantity": 4}],
                site=shop_user,
                external_ref="VCH-2026-0042",
                created_by=manager,
            )

        assert "VCH-2026-0042" in str(error.value)
        assert Item.objects.get(pk="SKU-1").quantity == 6
        assert StockDocument.objects.count() == 1

    def test_different_vouchers_both_move(self, manager, make_item, shop_user):
        make_item(sku="SKU-1", quantity=10)

        for voucher in ("VCH-1", "VCH-2"):
            service.create_document(
                doc_type=StockDocument.SITE_ISSUE,
                lines=[{"sku": "SKU-1", "quantity": 2}],
                site=shop_user,
                external_ref=voucher,
                created_by=manager,
            )

        assert Item.objects.get(pk="SKU-1").quantity == 6
        assert StockDocument.objects.count() == 2


class TestDocumentApi:
    def test_a_site_user_submission_is_pending_and_moves_nothing(
        self, shop_client, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=10)

        response = shop_client.post(
            "/api/documents/",
            {
                "doc_type": StockDocument.SITE_ISSUE,
                "site": shop_user.username,
                "lines": [{"sku": "SKU-1", "quantity": 3}],
            },
            format="json",
        )

        assert response.status_code == 201, response.content
        assert response.json()["status"] == StockDocument.PENDING
        assert Item.objects.get(pk="SKU-1").quantity == 10

    def test_a_manager_submission_is_applied_at_once(self, manager_client, make_item):
        make_item(sku="SKU-1", quantity=10)

        response = manager_client.post(
            "/api/documents/",
            {
                "doc_type": StockDocument.PO_RECEIPT,
                "counterparty": "Elsewedy",
                "lines": [{"sku": "SKU-1", "quantity": 5}],
            },
            format="json",
        )

        assert response.status_code == 201, response.content
        assert response.json()["status"] == StockDocument.APPROVED
        assert Item.objects.get(pk="SKU-1").quantity == 15

    def test_only_a_manager_can_decide(self, shop_client, shop_user, make_item):
        make_item(sku="SKU-1", quantity=10)
        document = service.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 2}],
            site=shop_user,
            created_by=shop_user,
            source=StockDocument.MOBILE,
        )

        refused = shop_client.post(
            f"/api/documents/{document.id}/decide/", {"action": "approve"}, format="json"
        )

        assert refused.status_code == 403
        assert Item.objects.get(pk="SKU-1").quantity == 10

    def test_a_manager_approval_applies_the_pending_document(
        self, manager_client, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=10)
        document = service.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 2}],
            site=shop_user,
            created_by=shop_user,
            source=StockDocument.MOBILE,
        )

        response = manager_client.post(
            f"/api/documents/{document.id}/decide/", {"action": "approve"}, format="json"
        )

        assert response.status_code == 200, response.content
        assert response.json()["status"] == StockDocument.APPROVED
        assert Item.objects.get(pk="SKU-1").quantity == 8

    def test_pending_documents_can_be_listed(self, manager_client, shop_user, make_item):
        make_item(sku="SKU-1", quantity=10)
        service.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 2}],
            site=shop_user,
            created_by=shop_user,
            source=StockDocument.MOBILE,
        )

        response = manager_client.get("/api/documents/?status=pending")

        assert response.status_code == 200
        assert response.json()["count"] == 1
        assert response.json()["results"][0]["status"] == StockDocument.PENDING


class TestDocumentPages:
    def test_the_manager_books_a_receipt_from_the_page(self, client, manager, make_item):
        make_item(sku="SKU-1", quantity=1)
        client.force_login(manager)

        response = client.post(
            "/receipts/",
            {
                "doc_type": StockDocument.PO_RECEIPT,
                "counterparty": "Elsewedy",
                "reference": "PO-2026-0009",
                "sku": ["SKU-1"],
                "quantity": ["4"],
            },
        )

        assert response.status_code == 302
        assert Item.objects.get(pk="SKU-1").quantity == 5
        assert StockDocument.objects.get().status == StockDocument.APPROVED

    def test_a_site_user_page_entry_waits_for_approval(
        self, client, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=10)
        client.force_login(shop_user)

        client.post(
            "/issues/",
            {
                "doc_type": StockDocument.SITE_ISSUE,
                "site": str(shop_user.id),
                "sku": ["SKU-1"],
                "quantity": ["3"],
            },
        )

        document = StockDocument.objects.get()
        assert document.status == StockDocument.PENDING
        assert Item.objects.get(pk="SKU-1").quantity == 10

    def test_a_site_user_cannot_approve_from_the_page(self, client, shop_user, make_item):
        make_item(sku="SKU-1", quantity=10)
        document = service.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 3}],
            site=shop_user,
            created_by=shop_user,
            source=StockDocument.MOBILE,
        )
        client.force_login(shop_user)

        client.post(f"/issues/{document.id}/approve/", {"next": "/issues/"})

        document.refresh_from_db()
        assert document.status == StockDocument.PENDING
        assert Item.objects.get(pk="SKU-1").quantity == 10

    def test_the_manager_approves_from_the_queue(self, client, manager, shop_user, make_item):
        make_item(sku="SKU-1", quantity=10)
        document = service.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 3}],
            site=shop_user,
            created_by=shop_user,
            source=StockDocument.MOBILE,
        )
        client.force_login(manager)

        client.post(f"/issues/{document.id}/approve/", {"next": "/issues/"})

        document.refresh_from_db()
        assert document.status == StockDocument.APPROVED
        assert Item.objects.get(pk="SKU-1").quantity == 7

    def test_every_page_is_behind_the_login(self, client):
        for url in ("/stock/", "/receipts/", "/issues/", "/issues/report/"):
            response = client.get(url)
            assert response.status_code == 302, url
            assert "/accounts/login/" in response["Location"]

    def test_the_dashboard_links_to_every_page(self, client, manager):
        """A page nobody can reach is a page that does not exist."""
        client.force_login(manager)

        html = client.get("/").content.decode()

        for url in ("/stock/", "/receipts/", "/issues/", "/issues/report/"):
            assert f'href="{url}"' in html, url
