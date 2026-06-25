from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Transaction:
    message_id: str
    bank: str
    amount: Optional[str]
    amount_value: Optional[float]
    currency: Optional[str]
    merchant: Optional[str]
    card_last4: Optional[str]
    transaction_date: Optional[str]
    authorization: Optional[str]
    email_from: str
    email_to: str
    email_subject: str
    email_date: str
    processed_at: str
    body: str

    def to_dict(self):
        return asdict(self)