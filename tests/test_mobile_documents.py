"""The warehouse flow on the phone: scan a label, photograph the voucher, submit.

Three properties are pinned here, and each of them is a rule rather than a
convenience:

* **A phone submission moves nothing.** The document is created ``pending``; the
  balance changes only when a manager approves it on the web.
* **The unit is the catalogue's.** An issue counted in metres must not become
  pieces because the phone sent a unit of its own.
* **A voucher is booked once.** The same voucher number cannot deduct stock
  twice, however many times the phone retries.
"""

import json
from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from stock_manager import documents as stock_documents
from stock_manager import mobile
from stock_manager.models import Item, StockDocument

pytestmark = pytest.mark.django_db

PASSWORD = "test-pass-123"
PHOTO = b"\xff\xd8\xff\xe0" + b"0" * 200  # a JPEG-ish blob; the server only checks the type


def post_json(client, path, payload, token=None):
    extra = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
    return client.post(
        path, data=json.dumps(payload), content_type="application/json", **extra
    )


@pytest.fixture
def phone_user(shop_user):
    mobile.set_phone(shop_user, "01012345678")
    return shop_user


@pytest.fixture
def token(client, phone_user):
    # The sign-in limiter is keyed on phone + address and lives in the cache,
    # which outlives a single test: without this, another suite's failed
    # attempts turn this fixture into a 429.
    from django.core.cache import cache

    cache.clear()
    response = post_json(
        client, "/api/mobile/login/", {"phone": "01012345678", "password": PASSWORD}
    )
    assert response.status_code == 200, response.content
    return response.json()["token"]


@pytest.fixture
def cable(db):
    return Item.objects.create(
        sku="CBL-3X25", description="Cable 3x2.5 mm", retail_price="12.50", quantity=100, unit="متر"
    )


@pytest.fixture
def socket(db):
    return Item.objects.create(
        sku="SKT-16A", description="Socket 16A", retail_price="45.00", quantity=40, unit="قطعة"
    )


def submit(client, token, **overrides):
    """A complete submission, with any field replaced by the caller.

    Multipart, because that is what the app sends: the voucher photograph rides
    in the same request as the fields it belongs to.
    """
    fields = {
        "direction": "out",
        "voucher": "050340604",
        "location": "مبنى B — الدور الثالث",
        "engineerName": "م. أحمد سمير",
        "documentDate": "2026-11-20",
        "notes": "توريد موقع",
        "lines": [{"code": "CBL-3X25", "quantity": 10}],
        "photo": PHOTO,
        "photo_type": "image/jpeg",
    }
    fields.update(overrides)
    photo = fields.pop("photo")
    photo_type = fields.pop("photo_type", "image/jpeg")
    fields["lines"] = json.dumps(fields["lines"])
    if photo:
        fields["photo"] = SimpleUploadedFile("voucher.jpg", photo, content_type=photo_type)
    return client.post(
        "/api/mobile/documents/",
        data=fields,
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


# --------------------------------------------------------------------- lookup


def test_a_scanned_label_resolves_to_the_item_and_its_unit(client, token, cable):
    response = client.get(
        "/api/mobile/items/lookup/?code=CBL-3X25",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert response.status_code == 200, response.content
    item = response.json()["item"]
    assert item["code"] == "CBL-3X25"
    assert item["unit"] == "متر"
    assert item["quantity"] == 100


def test_the_lookup_tolerates_a_scanner_that_adds_spaces_or_lowercase(client, token, cable):
    for code in ("cbl-3x25", " CBL-3X25 ", "CBL 3X25"):
        response = client.get(
            f"/api/mobile/items/lookup/?code={code}",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert response.status_code == 200, (code, response.content)


def test_an_unknown_label_is_refused_in_a_sentence_the_operator_can_act_on(client, token):
    response = client.get(
        "/api/mobile/items/lookup/?code=NOPE-1", HTTP_AUTHORIZATION=f"Bearer {token}"
    )
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "item_unknown"
    assert "NOPE-1" in body["error"]


def test_a_stopped_item_is_refused_rather_than_issued(client, token, cable):
    cable.is_active = False
    cable.save(update_fields=["is_active"])
    response = client.get(
        "/api/mobile/items/lookup/?code=CBL-3X25", HTTP_AUTHORIZATION=f"Bearer {token}"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "item_inactive"


def test_a_json_client_is_held_to_the_same_rules(client, token, cable):
    """The JSON branch is not a way around the photograph requirement."""
    response = post_json(
        client,
        "/api/mobile/documents/",
        {
            "direction": "out",
            "voucher": "J-1",
            "location": "موقع",
            "engineerName": "م. علي",
            "lines": [{"code": "CBL-3X25", "quantity": 1}],
        },
        token,
    )
    assert response.status_code == 400
    assert "صوّر" in response.json()["error"]


def test_the_lookup_needs_a_session(client, cable):
    response = client.get("/api/mobile/items/lookup/?code=CBL-3X25")
    assert response.status_code == 401


# ------------------------------------------------------------------- submitting


def test_a_phone_issue_is_pending_and_moves_nothing(client, token, cable):
    before = Item.objects.get(pk="CBL-3X25").quantity
    response = submit(client, token)
    assert response.status_code == 201, response.content
    document = StockDocument.objects.get(pk=response.json()["document"]["id"])
    assert document.status == StockDocument.PENDING
    assert document.source == StockDocument.MOBILE
    assert document.direction == StockDocument.OUT
    assert document.doc_type == StockDocument.SITE_ISSUE
    assert document.document_date == date(2026, 11, 20)
    assert document.location == "مبنى B — الدور الثالث"
    assert document.engineer_name == "م. أحمد سمير"
    assert document.external_ref == "050340604"
    assert document.photo
    assert document.photo_type == "image/jpeg"
    assert Item.objects.get(pk="CBL-3X25").quantity == before


def test_the_line_carries_the_catalogue_unit_even_when_the_phone_sends_another(
    client, token, cable
):
    response = submit(
        client,
        token,
        lines=[{"code": "CBL-3X25", "quantity": 7, "unit": "قطعة"}],
    )
    assert response.status_code == 201, response.content
    line = StockDocument.objects.get(pk=response.json()["document"]["id"]).lines.get()
    assert line.unit == "متر"


def test_an_addition_is_a_site_return_and_also_waits_for_approval(client, token, cable):
    response = submit(client, token, direction="in", voucher="RET-1")
    assert response.status_code == 201, response.content
    document = StockDocument.objects.get(pk=response.json()["document"]["id"])
    assert document.doc_type == StockDocument.SITE_RETURN
    assert document.direction == StockDocument.IN
    assert document.status == StockDocument.PENDING


@pytest.mark.parametrize(
    "field,code",
    [
        ("voucher", "voucher_required"),
        ("location", "location_required"),
        ("engineerName", "engineer_required"),
        ("lines", "lines_required"),
        ("direction", "direction_required"),
    ],
)
def test_every_field_the_paper_carries_is_required(client, token, cable, field, code):
    response = submit(client, token, **{field: ""})
    assert response.status_code == 400, response.content
    assert response.json()["code"] == code


def test_a_document_without_its_photograph_is_refused(client, token, cable):
    response = submit(client, token, photo=b"")
    assert response.status_code == 400
    assert "صوّر" in response.json()["error"]


def test_a_photo_of_the_wrong_kind_is_refused(client, token, cable):
    response = submit(client, token, photo_type="application/pdf")
    assert response.status_code == 400
    assert "صيغة" in response.json()["error"]


def test_an_unknown_scanned_code_is_refused_and_names_the_code(client, token, cable):
    response = submit(client, token, lines=[{"code": "NOPE-9", "quantity": 1}])
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "item_unknown"
    assert "NOPE-9" in body["error"]
    assert not StockDocument.objects.exists()


def test_a_quantity_of_zero_is_refused(client, token, cable):
    response = submit(client, token, lines=[{"code": "CBL-3X25", "quantity": 0}])
    assert response.status_code == 400
    assert response.json()["code"] == "bad_quantity"


def test_the_same_voucher_cannot_be_booked_twice(client, token, cable):
    assert submit(client, token).status_code == 201
    again = submit(client, token, lines=[{"code": "CBL-3X25", "quantity": 3}])
    assert again.status_code == 400
    assert again.json()["code"] == "document_refused"
    assert StockDocument.objects.count() == 1


def test_an_empty_date_is_today(client, token, cable):
    response = submit(client, token, documentDate="")
    assert response.status_code == 201, response.content
    document = StockDocument.objects.get(pk=response.json()["document"]["id"])
    assert document.document_date == date.today()


def test_a_malformed_date_is_refused_with_the_expected_shape(client, token, cable):
    response = submit(client, token, documentDate="20/11/2026")
    assert response.status_code == 400
    assert "2026-11-21" in response.json()["error"]


# ----------------------------------------------------------------------- list


def test_a_user_sees_their_own_documents_and_nothing_else(client, token, cable, manager):
    submit(client, token)
    other = stock_documents.create_document(
        doc_type=StockDocument.SITE_ISSUE,
        lines=[{"sku": "CBL-3X25", "quantity": 1}],
        location="مخزن آخر",
        created_by=manager,
        pending=True,
    )
    response = client.get(
        "/api/mobile/documents/", HTTP_AUTHORIZATION=f"Bearer {token}"
    )
    assert response.status_code == 200
    numbers = [row["number"] for row in response.json()["documents"]]
    assert len(numbers) == 1
    assert other.number not in numbers
    row = response.json()["documents"][0]
    assert row["status"] == StockDocument.PENDING
    assert row["hasPhoto"] is True
    assert row["lines"][0]["unit"] == "متر"


# -------------------------------------------------------------------- approval


def test_approving_the_phone_issue_deducts_the_stock(client, token, cable, manager):
    response = submit(client, token, lines=[{"code": "CBL-3X25", "quantity": 10}])
    document = StockDocument.objects.get(pk=response.json()["document"]["id"])
    stock_documents.approve_document(document, user=manager)
    assert Item.objects.get(pk="CBL-3X25").quantity == 90
    document.refresh_from_db()
    assert document.status == StockDocument.APPROVED
    assert document.decided_by == manager


def test_approving_the_phone_addition_adds_the_stock(client, token, cable, manager):
    response = submit(
        client, token, direction="in", voucher="RET-2", lines=[{"code": "CBL-3X25", "quantity": 5}]
    )
    document = StockDocument.objects.get(pk=response.json()["document"]["id"])
    stock_documents.approve_document(document, user=manager)
    assert Item.objects.get(pk="CBL-3X25").quantity == 105


def test_a_rejected_document_moves_nothing(client, token, cable, manager):
    response = submit(client, token, lines=[{"code": "CBL-3X25", "quantity": 10}])
    document = StockDocument.objects.get(pk=response.json()["document"]["id"])
    stock_documents.reject_document(document, user=manager, note="بند غير مطابق")
    assert Item.objects.get(pk="CBL-3X25").quantity == 100
    document.refresh_from_db()
    assert document.status == StockDocument.REJECTED


def test_an_issue_bigger_than_the_stock_is_refused_at_approval(client, token, cable, manager):
    """The shelf can empty between the submission and the approval.

    The phone sent a valid 100 of 100; a manager then issued 60 elsewhere. The
    approval must refuse rather than take the balance negative — the phone's
    check is the message, this one is the guarantee.
    """
    response = submit(client, token, lines=[{"code": "CBL-3X25", "quantity": 100}])
    document = StockDocument.objects.get(pk=response.json()["document"]["id"])

    Item.objects.filter(pk="CBL-3X25").update(quantity=40)
    with pytest.raises(stock_documents.DocumentError):
        stock_documents.approve_document(document, user=manager)

    assert Item.objects.get(pk="CBL-3X25").quantity == 40
    document.refresh_from_db()
    assert document.status == StockDocument.PENDING


# ------------------------------------------------------------- the review screen


def test_the_review_screen_shows_the_voucher_and_the_paper_fields(
    client, token, cable, manager
):
    response = submit(client, token)
    pk = response.json()["document"]["id"]
    client.force_login(manager)
    page = client.get(f"/documents/{pk}/")
    assert page.status_code == 200
    html = page.content.decode()
    assert "050340604" in html
    assert "مبنى B — الدور الثالث" in html
    assert "م. أحمد سمير" in html
    assert f"/documents/{pk}/photo/" in html
    assert "CBL-3X25" in html


def test_the_photograph_is_served_from_the_database(client, token, cable, manager):
    response = submit(client, token)
    pk = response.json()["document"]["id"]
    client.force_login(manager)
    photo = client.get(f"/documents/{pk}/photo/")
    assert photo.status_code == 200
    assert photo["Content-Type"] == "image/jpeg"
    assert photo.content == PHOTO


def test_the_review_screen_is_not_public(client, token, cable):
    response = submit(client, token)
    pk = response.json()["document"]["id"]
    Client().logout()
    anonymous = Client().get(f"/documents/{pk}/")
    assert anonymous.status_code in (301, 302)


def test_a_manager_can_approve_from_the_review_screen(client, token, cable, manager):
    response = submit(client, token, lines=[{"code": "CBL-3X25", "quantity": 4}])
    pk = response.json()["document"]["id"]
    client.force_login(manager)
    decided = client.post(f"/issues/{pk}/approve/", {"next": f"/documents/{pk}/"})
    assert decided.status_code == 302
    assert Item.objects.get(pk="CBL-3X25").quantity == 96


def test_the_pending_queue_links_to_the_review_screen(client, token, cable, manager):
    response = submit(client, token)
    pk = response.json()["document"]["id"]
    client.force_login(manager)
    page = client.get("/issues/")
    assert page.status_code == 200
    assert f"/documents/{pk}/" in page.content.decode()


def test_an_addition_waits_on_the_additions_page_too(client, token, cable, manager):
    response = submit(client, token, direction="in", voucher="RET-3")
    pk = response.json()["document"]["id"]
    client.force_login(manager)
    page = client.get("/receipts/")
    html = page.content.decode()
    assert f"/documents/{pk}/" in html
    # The issue queue is for issues: an addition must not appear twice.
    issues = client.get("/issues/").content.decode()
    assert f"/documents/{pk}/" not in issues


def test_the_web_form_records_the_same_paper_fields(client, cable, manager):
    client.force_login(manager)
    response = client.post(
        "/issues/",
        {
            "doc_type": StockDocument.SITE_ISSUE,
            "counterparty": "",
            "reference": "",
            "external_ref": "WEB-1",
            "document_date": "2026-11-01",
            "location": "محطة الرفع",
            "engineer_name": "م. سارة",
            "notes": "",
            "sku": "CBL-3X25",
            "description": "",
            "unit": "",
            "quantity": "2",
        },
    )
    assert response.status_code == 302
    document = StockDocument.objects.get(external_ref="WEB-1")
    assert document.document_date == date(2026, 11, 1)
    assert document.location == "محطة الرفع"
    assert document.engineer_name == "م. سارة"


# ------------------------------------------------------------ more than the shelf


def test_an_issue_larger_than_the_shelf_is_refused_at_the_phone(client, token, cable):
    response = submit(
        client, token, voucher="050399001", lines=[{"code": "CBL-3X25", "quantity": 101}]
    )

    assert response.status_code == 400
    message = response.json()["error"]
    # The operator must learn both numbers while still holding the phone.
    assert "CBL-3X25" in message
    assert "101" in message
    assert "100" in message
    assert StockDocument.objects.filter(external_ref="050399001").exists() is False


def test_issuing_exactly_what_is_on_the_shelf_is_allowed(client, token, cable):
    response = submit(
        client, token, voucher="050399002", lines=[{"code": "CBL-3X25", "quantity": 100}]
    )

    assert response.status_code == 201, response.content
    assert response.json()["document"]["status"] == "pending"


def test_two_lines_of_the_same_item_are_added_up_before_the_check(client, token, cable):
    """60 + 60 is 120 of 100 — two lines must not each pass on their own."""
    response = submit(
        client,
        token,
        voucher="050399003",
        lines=[
            {"code": "CBL-3X25", "quantity": 60},
            {"code": "CBL-3X25", "quantity": 60},
        ],
    )

    assert response.status_code == 400
    assert "120" in response.json()["error"]


def test_an_addition_is_not_capped_by_the_shelf(client, token, cable):
    response = submit(
        client,
        token,
        direction="in",
        voucher="050399004",
        lines=[{"code": "CBL-3X25", "quantity": 5000}],
    )

    assert response.status_code == 201, response.content
