"""The stock table stacks one internal code over its Oracle codes."""

import pytest
from playwright.sync_api import expect

from stock_manager import item_codes

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def test_the_default_stock_table_merges_the_rows_of_one_internal_code(
    page, live_server, login, manager, app_config, make_item
):
    first = make_item(sku="ORACLE-A", description="Nail 3in", quantity=5)
    second = make_item(sku="ORACLE-B", description="Nail 3in", quantity=7)
    group = item_codes.merge_codes([first.sku, second.sku])
    login("manager")

    page.goto(f"{live_server.url}/stock/")

    expect(page.locator("#itemTable1 tr")).to_have_count(2)
    expect(page.locator("#kpiWarehouse")).to_have_text("2")
    expect(page.locator("#kpiInternalCodes")).to_have_text("1")
    merged = page.locator("#itemTable1 td.sap-table__group[rowspan]")
    expect(merged).to_have_count(2)
    expect(merged.first).to_have_text(group.code)
    expect(merged.nth(1)).to_have_text("12")
    expect(page.locator("#itemTable1")).to_contain_text("ORACLE-A")
    expect(page.locator("#itemTable1")).to_contain_text("ORACLE-B")


def test_the_internal_codes_page_shows_the_group_and_its_total(
    page, live_server, login, manager, app_config, make_item
):
    first = make_item(sku="ORACLE-A", description="Nail 3in", quantity=5)
    second = make_item(sku="ORACLE-B", description="Nail 3in", quantity=7)
    group = item_codes.merge_codes([first.sku, second.sku])
    login("manager")

    page.goto(f"{live_server.url}/items/groups/")

    expect(page.locator("#internalCodesTable")).to_contain_text(group.code)
    expect(page.locator("#internalCodesTable")).to_contain_text("12")
    expect(page.locator("#oracleCodesTable")).to_contain_text("ORACLE-A")
    expect(page.locator("#oracleCodesTable")).to_contain_text("ORACLE-B")
