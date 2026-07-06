import pytest

from stock_manager.models import ShopItem, TransferItem

pytestmark = pytest.mark.django_db


def result_field(response, field):
    return [row[field] for row in response.json()["results"]]


class TestShopItemList:
    def test_anonymous_denied(self, api_client):
        assert api_client.get("/api/shop_items/").status_code == 403

    def test_user_sees_only_own_shop_items(
        self, shop_client, shop_user, other_shop_user, make_item
    ):
        mine = make_item(sku="MINE")
        theirs = make_item(sku="THEIRS")
        ShopItem.objects.create(shop_user=shop_user, item=mine, quantity=1)
        ShopItem.objects.create(shop_user=other_shop_user, item=theirs, quantity=1)

        response = shop_client.get("/api/shop_items/")
        assert result_field(response, "item_sku") == ["MINE"]

    def test_rows_with_deleted_item_excluded(self, shop_client, shop_user, make_item):
        item = make_item(sku="GONE")
        ShopItem.objects.create(shop_user=shop_user, item=item, quantity=1)
        item.delete()

        response = shop_client.get("/api/shop_items/")
        assert response.json()["results"] == []

    def test_search_matches_item_sku_and_description(
        self, shop_client, shop_user, make_item
    ):
        ShopItem.objects.create(
            shop_user=shop_user,
            item=make_item(sku="ABC", description="Bird feeder"),
            quantity=1,
        )
        ShopItem.objects.create(
            shop_user=shop_user,
            item=make_item(sku="XYZ", description="Dog lead"),
            quantity=1,
        )

        response = shop_client.get("/api/shop_items/?search=feeder")
        assert result_field(response, "item_sku") == ["ABC"]

    def test_sku_ordering_uses_natural_sort(self, shop_client, shop_user, make_item):
        for sku in ("S10", "S2", "S1"):
            ShopItem.objects.create(
                shop_user=shop_user, item=make_item(sku=sku), quantity=1
            )
        response = shop_client.get("/api/shop_items/?ordering=sku")
        assert result_field(response, "item_sku") == ["S1", "S2", "S10"]

    def test_default_ordering_is_most_recently_updated_first(
        self, shop_client, shop_user, make_item
    ):
        # A deterministic default ordering is required for stable pagination.
        ShopItem.objects.create(shop_user=shop_user, item=make_item(sku="FIRST"), quantity=1)
        ShopItem.objects.create(shop_user=shop_user, item=make_item(sku="SECOND"), quantity=1)
        response = shop_client.get("/api/shop_items/")
        assert result_field(response, "item_sku") == ["SECOND", "FIRST"]

    def test_retrieve_by_item_sku(self, shop_client, shop_user, make_item):
        ShopItem.objects.create(
            shop_user=shop_user, item=make_item(sku="SKU-1"), quantity=4
        )
        response = shop_client.get("/api/shop_items/SKU-1/")
        assert response.status_code == 200
        assert response.json()["quantity"] == 4

    def test_cannot_retrieve_other_users_shop_item(
        self, shop_client, other_shop_user, make_item
    ):
        ShopItem.objects.create(
            shop_user=other_shop_user, item=make_item(sku="SKU-1"), quantity=4
        )
        assert shop_client.get("/api/shop_items/SKU-1/").status_code == 404


class TestTransferItemList:
    def test_anonymous_denied(self, api_client):
        assert api_client.get("/api/transfer_items/").status_code == 403

    def test_shop_user_sees_own_transfers_ordered_or_not(
        self, shop_client, shop_user, other_shop_user, make_item
    ):
        TransferItem.objects.create(
            shop_user=shop_user, item=make_item(sku="PENDING"), quantity=1
        )
        TransferItem.objects.create(
            shop_user=shop_user,
            item=make_item(sku="ORDERED"),
            quantity=1,
            ordered=True,
        )
        TransferItem.objects.create(
            shop_user=other_shop_user, item=make_item(sku="OTHER"), quantity=1
        )

        response = shop_client.get("/api/transfer_items/")
        skus = {row["item"]["sku"] for row in response.json()["results"]}
        assert skus == {"PENDING", "ORDERED"}

    def test_manager_sees_only_submitted_transfers_from_all_users(
        self, manager_client, shop_user, other_shop_user, make_item
    ):
        TransferItem.objects.create(
            shop_user=shop_user, item=make_item(sku="DRAFT"), quantity=1
        )
        TransferItem.objects.create(
            shop_user=shop_user,
            item=make_item(sku="SENT-1"),
            quantity=1,
            ordered=True,
        )
        TransferItem.objects.create(
            shop_user=other_shop_user,
            item=make_item(sku="SENT-2"),
            quantity=1,
            ordered=True,
        )

        response = manager_client.get("/api/transfer_items/")
        skus = {row["item"]["sku"] for row in response.json()["results"]}
        assert skus == {"SENT-1", "SENT-2"}

    def test_default_ordering_is_most_recently_updated_first(
        self, shop_client, shop_user, make_item
    ):
        # A deterministic default ordering is required for stable pagination.
        TransferItem.objects.create(
            shop_user=shop_user, item=make_item(sku="FIRST"), quantity=1
        )
        TransferItem.objects.create(
            shop_user=shop_user, item=make_item(sku="SECOND"), quantity=1
        )
        response = shop_client.get("/api/transfer_items/")
        skus = [row["item"]["sku"] for row in response.json()["results"]]
        assert skus == ["SECOND", "FIRST"]

    def test_search_filters_by_item(self, shop_client, shop_user, make_item):
        TransferItem.objects.create(
            shop_user=shop_user,
            item=make_item(sku="AAA", description="Bird feeder"),
            quantity=1,
        )
        TransferItem.objects.create(
            shop_user=shop_user,
            item=make_item(sku="BBB", description="Dog lead"),
            quantity=1,
        )
        response = shop_client.get("/api/transfer_items/?search=bird")
        skus = [row["item"]["sku"] for row in response.json()["results"]]
        assert skus == ["AAA"]

    def test_sku_ordering_uses_natural_sort(self, shop_client, shop_user, make_item):
        for sku in ("T10", "T2", "T1"):
            TransferItem.objects.create(
                shop_user=shop_user, item=make_item(sku=sku), quantity=1
            )
        response = shop_client.get("/api/transfer_items/?ordering=sku")
        skus = [row["item"]["sku"] for row in response.json()["results"]]
        assert skus == ["T1", "T2", "T10"]
