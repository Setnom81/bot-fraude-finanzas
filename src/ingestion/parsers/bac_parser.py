"""
BAC Parser

Responsible for converting the content of a BAC transaction
notification email into a Transaction object.

If support for additional banks is added in the future,
each bank should have its own dedicated parser
(e.g., PromericaParser, BNParser, etc.).
"""

import re
from datetime import datetime

from src.core.models import Transaction


class BacParser:
    """
    Parses BAC email notifications and extracts structured
    transaction information.

    Each extraction method is responsible for retrieving a
    specific piece of data from the email body.
    """

    # ==========================================================
    # PUBLIC API
    # ==========================================================

    def parse(self, message_id, headers, body, gmail_client):
        """
        Converts a Gmail message into a Transaction object.

        Args:
            message_id (str): Gmail message identifier.
            headers (list): Gmail message headers.
            body (str): Plain text email body.
            gmail_client (GmailClient): Gmail helper used to
                retrieve header values.

        Returns:
            Transaction: Parsed transaction data.
        """

        # Extracts the raw amount first so it can be reused by
        # the amount value and currency extraction methods.
        amount_raw = self.extract_amount_raw(body)

        return Transaction(
            message_id=message_id,

            bank="BAC",

            amount=amount_raw,

            amount_value=self.extract_amount_value(amount_raw),

            currency=self.extract_currency(amount_raw),

            merchant=self.extract_merchant(body),

            card_last4=self.extract_card_last4(body),

            transaction_date=self.extract_transaction_date(body),

            authorization=self.extract_authorization(body),

            email_from=gmail_client.get_header(headers, "From"),

            email_to=gmail_client.get_header(headers, "To"),

            email_subject=gmail_client.get_header(headers, "Subject"),

            email_date=gmail_client.get_header(headers, "Date"),

            # Records when the parser processed this email.
            processed_at=datetime.now().isoformat(),

            # Stores the original email body for auditing
            # and future troubleshooting.
            body=body
        )

    # ==========================================================
    # TEXT UTILITIES
    # ==========================================================

    @staticmethod
    def clean_text(text):
        """
        Normalizes whitespace by removing repeated spaces
        and line breaks.

        Args:
            text (str): Raw email text.

        Returns:
            str: Cleaned text.
        """

        return " ".join(text.split())

    # ==========================================================
    # AMOUNT
    # ==========================================================

    def extract_amount_raw(self, body):
        """
        Extracts the transaction amount exactly as it appears
        in the email.

        Examples:
            ₡12,500.00
            USD 25.75
            $50.00

        Args:
            body (str): Email body.

        Returns:
            str | None: Raw amount string.
        """

        match = re.search(

            r"(₡|CRC|USD|\$)\s?[\d.,]+",

            self.clean_text(body),

            re.IGNORECASE

        )

        return match.group(0) if match else None

    def extract_currency(self, amount):
        """
        Determines the transaction currency from the amount.

        Args:
            amount (str): Raw amount string.

        Returns:
            str | None: Currency code (CRC or USD).
        """

        if not amount:
            return None

        amount = amount.upper()

        if "₡" in amount or "CRC" in amount:
            return "CRC"

        if "$" in amount or "USD" in amount:
            return "USD"

        return None

    def extract_amount_value(self, amount):
        """
        Converts the extracted amount into a numeric value.

        Example:
            ₡12,500.75

        becomes:

            12500.75

        Args:
            amount (str): Raw amount string.

        Returns:
            float | None: Parsed amount.
        """

        if not amount:
            return None

        value = (

            amount.upper()

            .replace("CRC", "")

            .replace("USD", "")

            .replace("₡", "")

            .replace("$", "")

            .strip()

        )

        # BAC emails typically use commas as thousands
        # separators, so they are removed before converting
        # the value to a float.
        value = value.replace(",", "")

        try:
            return float(value)

        except ValueError:
            return None

    # ==========================================================
    # MERCHANT
    # ==========================================================

    def extract_merchant(self, body):
        """
        Attempts to extract the merchant or business name
        from the email.

        Args:
            body (str): Email body.

        Returns:
            str | None: Merchant name.
        """

        match = re.search(

            r"(?:comercio|establecimiento|afiliado|local|empresa)\s*[:\-]?\s*(.+?)(?:fecha|monto|tarjeta|autorizaci[oó]n|referencia|$)",

            self.clean_text(body),

            re.IGNORECASE

        )

        return match.group(1).strip() if match else None

    # ==========================================================
    # CARD INFORMATION
    # ==========================================================

    def extract_card_last4(self, body):
        """
        Extracts the last four digits of the card used
        for the transaction.

        Args:
            body (str): Email body.

        Returns:
            str | None: Last four card digits.
        """

        match = re.search(

            r"(?:tarjeta|terminada en|finalizada en|últimos|ultimos|x{2,}|\*{2,})\s*(\d{4})",

            self.clean_text(body),

            re.IGNORECASE

        )

        return match.group(1) if match else None

    # ==========================================================
    # TRANSACTION DATE
    # ==========================================================

    def extract_transaction_date(self, body):
        """
        Searches the email for a transaction date.

        Args:
            body (str): Email body.

        Returns:
            str | None: Extracted date.
        """

        match = re.search(

            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",

            self.clean_text(body)

        )

        return match.group(0) if match else None

    # ==========================================================
    # AUTHORIZATION
    # ==========================================================

    def extract_authorization(self, body):
        """
        Extracts the authorization or reference code
        associated with the transaction.

        Args:
            body (str): Email body.

        Returns:
            str | None: Authorization/reference code.
        """

        match = re.search(

            r"(?:autorizaci[oó]n|autorizacion|aprobaci[oó]n|referencia)\s*[:#-]?\s*([A-Z0-9-]+)",

            self.clean_text(body),

            re.IGNORECASE

        )

        return match.group(1) if match else None