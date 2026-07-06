import pytest

from stock_manager.pagination import CustomPagination

pytestmark = pytest.mark.django_db


class FakeRequest:
    def __init__(self, **params):
        self.query_params = params


class TestGetPageSize:
    def test_uses_admin_configured_value(self, app_config):
        app_config.records_per_page = 7
        app_config.save()
        assert CustomPagination().get_page_size(FakeRequest()) == 7

    def test_query_param_overrides_config(self, app_config):
        assert CustomPagination().get_page_size(FakeRequest(page_size="3")) == 3

    def test_falls_back_to_25_without_config_row(self, db):
        assert CustomPagination().get_page_size(FakeRequest()) == 25

    def test_falls_back_to_25_on_invalid_param(self, app_config):
        assert CustomPagination().get_page_size(FakeRequest(page_size="bogus")) == 25

    def test_page_size_capped_at_max(self, app_config):
        pagination = CustomPagination()
        assert pagination.get_page_size(FakeRequest(page_size="500")) == (
            pagination.max_page_size
        )

    @pytest.mark.parametrize("non_positive", ["0", "-5"])
    def test_non_positive_page_size_falls_back_to_25(self, app_config, non_positive):
        assert (
            CustomPagination().get_page_size(FakeRequest(page_size=non_positive)) == 25
        )


class TestPaginatedResponseShape:
    def test_response_contains_custom_keys(self, app_config, manager_client, make_item):
        app_config.records_per_page = 2
        app_config.save()
        for i in range(5):
            make_item(sku=f"SKU-{i}")

        response = manager_client.get("/api/items/")

        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {
            "results",
            "current_page",
            "total_pages",
            "previous",
            "next",
            "previous_page_number",
            "next_page_number",
        }
        assert len(data["results"]) == 2
        assert data["current_page"] == 1
        assert data["total_pages"] == 3
        assert data["previous"] is None
        assert data["next_page_number"] == 2

    def test_last_page_links(self, app_config, manager_client, make_item):
        app_config.records_per_page = 2
        app_config.save()
        for i in range(5):
            make_item(sku=f"SKU-{i}")

        response = manager_client.get("/api/items/?page=3")

        data = response.json()
        assert len(data["results"]) == 1
        assert data["next"] is None
        assert data["next_page_number"] is None
        assert data["previous_page_number"] == 2
