import pytest
from django.contrib.auth.models import User

from email_service.email import SendEmail

pytestmark = pytest.mark.django_db


@pytest.fixture
def notifications_enabled(app_config):
    app_config.allow_email_notifications = True
    app_config.save()
    return app_config


@pytest.fixture
def recipient(groups):
    user = User.objects.create_user(
        username="warehouse", password="x", email="warehouse@example.com"
    )
    user.groups.add(groups["receive_mail"])
    return user


def sample_records():
    return [
        {
            "id": 1,
            "item__sku": "SKU-1",
            "item__description": "Widget",
            "item__retail_price": "9.99",
            "quantity": 3,
        }
    ]


class TestEmailValidate:
    def test_valid_address_passes(self, db):
        sender = SendEmail()
        sender.email_validate("someone@example.com")
        assert sender.email_invalid is False

    @pytest.mark.parametrize("bad", ["not-an-email", "@nouser.com", None])
    def test_invalid_address_flags_instance(self, db, bad):
        sender = SendEmail()
        sender.email_validate(bad)
        assert sender.email_invalid is True


class TestSend:
    def kwargs(self, **overrides):
        base = {
            "body_plaintext": "plain body",
            "body_html": "<p>html body</p>",
            "email_to": ["to@example.com"],
            "email_from": "from@example.com",
        }
        base.update(overrides)
        return base

    def test_returns_false_without_bodies_or_recipients(self, notifications_enabled):
        assert SendEmail().send(**self.kwargs(body_plaintext=None)) is False
        assert SendEmail().send(**self.kwargs(body_html=None)) is False
        assert SendEmail().send(**self.kwargs(email_to=[])) is False
        assert SendEmail().send(**self.kwargs(email_to="not-a-list")) is False

    def test_empty_recipient_entries_ignored(self, notifications_enabled, mailoutbox):
        result = SendEmail().send(**self.kwargs(email_to=["", "to@example.com"]))
        assert result is True
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == ["to@example.com"]

    def test_returns_false_for_invalid_recipient(
        self, notifications_enabled, mailoutbox
    ):
        result = SendEmail().send(**self.kwargs(email_to=["not-an-email"]))
        assert result is False
        assert len(mailoutbox) == 0

    def test_sends_when_notifications_enabled(self, notifications_enabled, mailoutbox):
        result = SendEmail().send(**self.kwargs())
        assert result is True
        assert len(mailoutbox) == 1
        message = mailoutbox[0]
        assert message.subject == SendEmail.DEFAULT_SUBJECT
        assert message.to == ["to@example.com"]
        assert message.body == "plain body"
        assert message.alternatives == [("<p>html body</p>", "text/html")]

    def test_custom_subject_used(self, notifications_enabled, mailoutbox):
        SendEmail().send(**self.kwargs(subject="Custom subject"))
        assert mailoutbox[0].subject == "Custom subject"

    def test_suppressed_when_notifications_disabled(self, app_config, mailoutbox):
        # Returns True (the call 'succeeded') but nothing is sent.
        result = SendEmail().send(**self.kwargs())
        assert result is True
        assert len(mailoutbox) == 0


class TestCompose:
    def test_stock_transfer_notification_sent(
        self, notifications_enabled, recipient, shop_user, mailoutbox
    ):
        result = SendEmail().compose(
            records=sample_records(),
            user=shop_user,
            notification_type=SendEmail.EmailType.STOCK_TRANSFER,
        )

        assert result is True
        assert len(mailoutbox) == 1
        message = mailoutbox[0]
        assert message.to == ["warehouse@example.com"]
        assert "SKU-1" in message.body
        assert "Widget" in message.body
        assert shop_user.username in message.body
        html_body = message.alternatives[0][0]
        assert "SKU-1" in html_body

    def test_duplicate_recipient_addresses_deduplicated(
        self, notifications_enabled, recipient, groups, shop_user, mailoutbox
    ):
        twin = User.objects.create_user(
            username="warehouse2", password="x", email="warehouse@example.com"
        )
        twin.groups.add(groups["receive_mail"])

        SendEmail().compose(
            records=sample_records(),
            user=shop_user,
            notification_type=SendEmail.EmailType.STOCK_TRANSFER,
        )

        assert mailoutbox[0].to == ["warehouse@example.com"]

    def test_returns_false_without_recipients(
        self, notifications_enabled, shop_user, mailoutbox
    ):
        result = SendEmail().compose(
            records=sample_records(),
            user=shop_user,
            notification_type=SendEmail.EmailType.STOCK_TRANSFER,
        )
        assert result is False
        assert len(mailoutbox) == 0

    def test_returns_false_for_unknown_notification_type(
        self, notifications_enabled, recipient, shop_user, mailoutbox
    ):
        result = SendEmail().compose(
            records=sample_records(),
            user=shop_user,
            notification_type="something-else",
        )
        assert result is False
        assert len(mailoutbox) == 0
