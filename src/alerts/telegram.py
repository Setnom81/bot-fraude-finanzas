import logging
from typing import Any, Dict, Optional
import requests

from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send_telegram_alert(
    transaction: Dict[str, Any], risk_score: Optional[float] = None
) -> None:
    """Dispatches an HTML-formatted notification payload to the specified Telegram Chat ID

    via the Telegram Bot API when a high-risk transaction is flagged.

    Args:
        transaction (Dict[str, Any]): Dictionary containing extracted transaction entity payload
            (expected keys: 'amount', 'currency', 'merchant', 'transaction_date').
        risk_score (Optional[float]): Evaluated hybrid risk confidence score or percentage value.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning(
            "Telegram notification skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID "
            "is unconfigured in environment."
        )
        return

    # Extract transaction entity attributes with default fallbacks
    amount: float = transaction.get("amount", 0.0)
    currency: str = transaction.get("currency", "CRC")
    merchant: str = transaction.get("merchant", "Unknown")
    date_str: str = str(transaction.get("transaction_date", "N/A"))

    # Construct HTML formatted message payload for Telegram Bot API
    message = (
        f"<b>Amount:</b> {currency} {amount:,.2f}\n"
        f"<b>Merchant:</b> {merchant}\n"
        f"<b>Date:</b> {date_str}\n"
    )

    if risk_score is not None:
        message += f"<b>Risk Score:</b> {risk_score:.2%}\n"

    message += "\n<i>Please verify this transaction if unrecognised.</i>"

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logging.info("Telegram notification payload successfully dispatched.")
        else:
            logging.error(
                f"Failed to dispatch Telegram alert. HTTP Status: {response.status_code} - Response: {response.text}"
            )
    except Exception as e:
        logging.error(
            f"Network Exception encountered while calling Telegram API endpoint: {e}"
        )