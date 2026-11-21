"""The table ordering contract, and that it is implemented once.

The three collections share this behaviour; the point of the module is that a
fix lands on all of them, so the last test pins the sharing itself.
"""

import pytest

from stock_manager.models import Item
from stock_manager.ordering import apply_ordering

pytestmark = pytest.mark.django_db


@pytest.fixture
def items():
    Item.objects.create(
        sku="ITEM-10", description="zeta", quantity=5, retail_price=10
    )
    Item.objects.create(
        sku="ITEM-2", description="Alpha", quantity=50, retail_price=10
    )
    Item.objects.create(
        sku="ITEM-1", description="beta", quantity=0, retail_price=10
    )
    return Item.objects.all()


def skus(rows):
    return [row.sku for row in rows]


class TestNaturalSort:
    def test_item_codes_sort_naturally(self, items):
        rows = apply_ordering(items, "sku", natural_key=lambda row: row.sku)

        assert skus(rows) == ["ITEM-1", "ITEM-2", "ITEM-10"]

    def test_the_direction_is_honoured(self, items):
        rows = apply_ordering(items, "-sku", natural_key=lambda row: row.sku)

        assert skus(rows) == ["ITEM-10", "ITEM-2", "ITEM-1"]

    def test_a_row_without_a_code_does_not_break_the_sort(self, items):
        # Site stock reaches the code through the related item, which may be null.
        rows = apply_ordering(
            list(items), "sku", natural_key=lambda row: row.sku if row.sku else None
        )

        assert len(rows) == 3


class TestOtherColumns:
    def test_quantity_sorts_as_a_number_not_as_text(self, items):
        rows = apply_ordering(items, "quantity", natural_key=lambda row: row.sku)

        assert [row.quantity for row in rows] == [0, 5, 50]

    def test_quantity_sorts_descending(self, items):
        rows = apply_ordering(items, "-quantity", natural_key=lambda row: row.sku)

        assert [row.quantity for row in rows] == [50, 5, 0]

    def test_text_sorts_case_insensitively(self, items):
        rows = apply_ordering(items, "description", natural_key=lambda row: row.sku)

        assert [row.description for row in rows] == ["Alpha", "beta", "zeta"]

    def test_no_ordering_falls_back_to_the_stable_default(self, items):
        rows = apply_ordering(items, None, natural_key=lambda row: row.sku)

        assert len(rows) == 3
        assert "last_updated" in str(rows.query).lower()


class TestOneImplementation:
    def test_the_viewsets_delegate_instead_of_repeating_the_branches(self):
        from pathlib import Path

        source = (
            Path(__file__).resolve().parent.parent / "stock_manager" / "views.py"
        ).read_text(encoding="utf-8")

        assert source.count("apply_ordering(") == 3
        # The branches themselves must not reappear in the views.
        assert "natsorted(" not in source
        assert 'ordering.lstrip("-")' not in source
