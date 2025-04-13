__Author__ = "Dan Bright, shout@zaziork.com"
__Copyright__ = "(c) Copyright 2021 Dan Bright"
__License__ = "GPL v3.0"
__Version__ = "Version 4.1"

import logging
from anymail.exceptions import AnymailAPIError
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.contrib.auth.models import User
from stock_manager.models import Admin
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from datetime import datetime
import pytz

# Get an instance of a logger
logger = logging.getLogger("django")


class SendEmail:
    DEFAULT_SUBJECT = "[SSM - NEW ORDER NOTIFICATION]"

    class EmailType:
        STOCK_TRANSFER = "Notification email sent when stock has been transferred"

    def __init__(self):
        self.email_invalid = False

    def email_validate(self, email=None):
        try:
            validate_email(email)
        except ValidationError as v:
            logger.error(f"Email {email} invalid!: {v}")
            self.email_invalid = True

    def send(
        self,
        body_plaintext=None,
        body_html=None,
        email_to=None,
        email_from=None,
        subject=None,
    ):
        email_to = [] if not isinstance(email_to, list) else email_to
        if body_plaintext and body_html and email_to:
            # validate email addresses first
            for c, e in enumerate(email_to):
                if e == "":  # remove any empty email addresses
                    email_to.pop(c)
                self.email_validate(e)
            self.email_validate(email_from)
            if not self.email_invalid:
                try:
                    if Admin.is_allow_email_notifications():
                        msg = EmailMultiAlternatives(
                            subject if subject else SendEmail.DEFAULT_SUBJECT,
                            body_plaintext,
                            email_from,
                            email_to,
                        )
                        msg.attach_alternative(body_html, "text/html")
                        # you can set any other options on msg here, then...
                        msg.send()
                    else:
                        logger.info(
                            f"If in live mode, notification email would be sent to: "
                            f'{[a for a in email_to] if email_to else "Nobody!"}'
                            f"The plaintext email body would read: {body_plaintext}"
                            f"The html email body would read: {body_html}"
                        )
                    return True
                except AnymailAPIError as e:
                    logger.error(
                        f"An error has occurred in sending email: {e.describe_response()}"
                    )
                except Exception as e:
                    logger.error(f"Error sending email: {e}")
        return False

    def compose(
        self,
        records: list = [],
        user: User = None,
        pre_formatted: dict = None,
        notification_type: str = None,
        subject: str = None,
    ) -> send:
        """
        :param records: ordered lines
        :param user: user making the update
        :param notification_type: type of notification to send
        :return: True|False
        This method composes notification emails, then sends them through the send() method.
        """

        def compose_body(ordered_items=[], user=None):
            formatted_time = datetime.now(pytz.timezone("EUROPE/LONDON")).strftime(
                "%d %b %Y %H:%M:%S %Z"
            )
            body_plaintext = [
                f"""The following order has been placed by {user.username} [{user.email}] on {formatted_time}."""
            ]
            body_html = [
                f"""<p>The following order has been placed by {user.username} [<a href="mailto:{user.email}">{user.email}</a>] on {formatted_time}. """
            ]
            if ordered_items:
                for stock_record in ordered_items:
                    body_plaintext.append(
                        f"""
                                    Stock Order Details:
                                      - SKU: {stock_record['item__sku']}
                                      - Description: {stock_record['item__description']}
                                      - Units transferred: {stock_record['quantity']}
                                      - Unit price: {stock_record['item__retail_price']}
                                    """
                    )
                    body_html.append(
                        f"""        <h2>Stock Order Details</h2>
                                    <ul>
                                    <li>SKU: {stock_record['item__sku']}</li>
                                    <li>Description: {stock_record['item__description']}</li>
                                    <li>Units transferred: {stock_record['quantity']}</li>
                                    <li>Unit price: {stock_record['item__retail_price']}</li>
                                    </ul>
                                    """
                    )
            return body_plaintext, body_html

        try:
            if notification_type == SendEmail.EmailType.STOCK_TRANSFER:
                """
                email a notification
                """
                send_to_addresses = User.objects.filter(
                    groups__name="receive_mail"
                ).values_list("email", flat=True)
                # list of all stock administrator's email addresses
                recipient_list = (
                    [a for a in send_to_addresses] if send_to_addresses else []
                )
                recipient_list = list(set(recipient_list))  # remove any dupes
                # add successful updates and failure response records to lists, ready for return in email notification
                if recipient_list:
                    body_plaintext, body_html = compose_body(
                        ordered_items=records, user=user
                    )
                    html_start = "<html><head></head><body>"
                    html_divider = "<br/><hr/><br/>"
                    html_end = "</body><footer><hr></footer></html>"

                    plaintext = f"""
                    Stock Transfer Request

                    {' '.join([b for b in body_plaintext])}

                    """

                    html = (
                        html_start
                        + "<h1>Stock Transfer Request</h1>"
                        + "".join([b for b in body_html])
                        + html_divider
                        + html_end
                    )
                    return self.send(
                        body_plaintext=plaintext,
                        body_html=html,
                        email_to=recipient_list,
                        email_from=settings.DEFAULT_FROM_EMAIL,
                        subject="[STOCK MANAGEMENT] A transfer request been placed.",
                    )
        except Exception as e:
            logger.error(f"An error occurred whilst attempting to send email: {str(e)}")
        return False
