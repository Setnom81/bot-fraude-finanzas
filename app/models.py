# Imports the dataclass decorator for automatically generating
# boilerplate methods (e.g., __init__, __repr__, __eq__) and
# the asdict utility for converting dataclass instances into dictionaries.
from dataclasses import dataclass, asdict

# Imports the Optional type hint to indicate fields that may
# contain a value or None.
from typing import Optional


@dataclass
class Transaction:
    """
    Represents a transaction extracted from a bank notification email.

    This model stores both the parsed transaction details and the
    original email metadata for auditing and traceability purposes.
    """

    # Unique Gmail message identifier.
    message_id: str

    # Name of the issuing bank.
    bank: str

    # Original transaction amount as it appears in the email.
    amount: Optional[str]

    # Numeric representation of the transaction amount.
    amount_value: Optional[float]

    # Transaction currency (e.g., CRC, USD).
    currency: Optional[str]

    # Merchant or business where the transaction occurred.
    merchant: Optional[str]

    # Last four digits of the card used.
    card_last4: Optional[str]

    # Date and time of the transaction, if available.
    transaction_date: Optional[str]

    # Bank authorization code.
    authorization: Optional[str]

    # Sender email address.
    email_from: str

    # Recipient email address.
    email_to: str

    # Email subject.
    email_subject: str

    # Email timestamp.
    email_date: str

    # Timestamp indicating when the transaction was processed.
    processed_at: str

    # Full email body used during parsing.
    body: str

    def to_dict(self):
        """
        Converts the Transaction object into a dictionary.

        Returns:
            dict: Dictionary representation of the transaction.
        """
        return asdict(self)