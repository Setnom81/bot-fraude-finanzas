import html
import logging
import time
from typing import Any, Dict, List

import requests

from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def _esc(value: Any) -> str:
    """Escapes text for Telegram's HTML parse mode."""
    return html.escape(str(value), quote=False)


def send_telegram_message(text: str, retries: int = 3) -> bool:
    """Sends an HTML-formatted message to the configured chat.

    Returns:
        bool: True only if Telegram accepted the message.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning(
            "Telegram message not sent: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not configured."
        )
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    for attempt in range(1, retries + 1):
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logging.info("Telegram message delivered.")
                return True
            logging.error(
                "Telegram rejected the message (attempt %d/%d). HTTP %s: %s",
                attempt, retries, response.status_code, response.text,
            )
            # 4xx other than rate limiting will not succeed on retry.
            if 400 <= response.status_code < 500 and response.status_code != 429:
                return False
        except requests.RequestException as e:
            # Do not log the exception text: it contains the bot token in the URL.
            logging.error(
                "Network error calling Telegram (attempt %d/%d): %s",
                attempt, retries, type(e).__name__,
            )
        if attempt < retries:
            time.sleep(2 * attempt)

    return False


def format_alert(result: Dict[str, Any]) -> str:
    """Builds the alert text for one scored transaction (see ml.inference)."""
    amount = float(result.get("amount") or 0.0)
    currency = result.get("currency") or ""
    local_time = result.get("local_time")
    when = local_time.strftime("%d-%m-%Y %H:%M") if local_time else "N/A"
    score = min(float(result.get("risk_score") or 0.0), 100.0)

    lines: List[str] = [
        "🚨 <b>HIGH RISK TRANSACTION DETECTED</b> 🚨",
        "",
        f"<b>Amount:</b> {_esc(currency)} {amount:,.2f}",
        f"<b>Merchant:</b> {_esc(result.get('merchant') or 'Unknown')}",
    ]
    if result.get("location"):
        lines.append(f"<b>Location:</b> {_esc(result['location'])}")
    if result.get("card_last4"):
        lines.append(f"<b>Card:</b> ****{_esc(result['card_last4'])}")
    lines.append(f"<b>Date:</b> {_esc(when)}")
    lines.append(f"<b>Risk Score:</b> {score:.2f}%")
    if result.get("reasons"):
        lines.append(f"<b>Why:</b> {_esc(', '.join(result['reasons']))}")
    lines += ["", "<i>Please verify this transaction if unrecognised.</i>"]
    return "\n".join(lines)


def send_telegram_alert(result: Dict[str, Any]) -> bool:
    """Sends the high-risk alert for one scored transaction."""
    return send_telegram_message(format_alert(result))
