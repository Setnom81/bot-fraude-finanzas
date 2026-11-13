from datetime import datetime, timezone
import logging
import re
from typing import Any, List, Optional

from O365 import Account, FileSystemTokenBackend

from src.config import (
    OUTLOOK_CLIENT_ID,
    OUTLOOK_CLIENT_SECRET,
    OUTLOOK_SUBJECT,
    OUTLOOK_TOKEN_DIR,
    OUTLOOK_TOKEN_FILENAME,
)


class OutlookAuthError(RuntimeError):
    """Outlook credentials are missing or the saved login is no longer valid."""


def build_account() -> Account:
    """Creates the O365 account bound to the token file in the project root."""
    if not OUTLOOK_CLIENT_ID or not OUTLOOK_CLIENT_SECRET:
        raise OutlookAuthError(
            "OUTLOOK_CLIENT_ID or OUTLOOK_CLIENT_SECRET is missing in src/.env."
        )
    token_backend = FileSystemTokenBackend(
        token_path=OUTLOOK_TOKEN_DIR, token_filename=OUTLOOK_TOKEN_FILENAME
    )
    return Account(
        (OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET), token_backend=token_backend
    )


class OutlookClient:
    """Read-only wrapper around the Outlook inbox via the O365 library.

    It never starts an interactive login: that needs a person at a terminal.
    Run 'python -m src.outlook_login' for that.
    """

    def __init__(self) -> None:
        self.account: Account = build_account()
        if not self.account.is_authenticated:
            raise OutlookAuthError(
                "No valid Outlook login found. Run 'python -m src.outlook_login' "
                "in the project folder to sign in again."
            )
        logging.info("Outlook session loaded from the cached token.")

    def search_messages(
        self, query: Optional[str] = None, since: Optional[datetime] = None
    ) -> List[Any]:
        """Returns inbox messages whose subject matches the bank notification.

        Args:
            query: Legacy Gmail-style query; only an 'after:YYYY/MM/DD' part is used.
            since: Only messages received at or after this moment (UTC).
        """
        if since is None and query and "after:" in query:
            try:
                date_part = query.split("after:")[-1].strip().split()[0]
                since = datetime.strptime(date_part, "%Y/%m/%d").replace(tzinfo=timezone.utc)
            except Exception as e:
                logging.warning(f"Could not read the date in query '{query}': {e}")

        subject = (OUTLOOK_SUBJECT or "").replace("'", "''")
        filter_clauses = [f"contains(subject, '{subject}')"]

        if since is not None:
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            iso_date = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            filter_clauses.append(f"receivedDateTime ge {iso_date}")

        odata_filter = " and ".join(filter_clauses)
        inbox = self.account.mailbox().inbox_folder()
        return list(inbox.get_messages(limit=9999, query=odata_filter))

    def get_message(self, message_id: str) -> Optional[Any]:
        """Fetches one message by its ID."""
        return self.account.mailbox().get_message(message_id)

    def get_header(self, message: Any, name: str) -> str:
        """Returns subject, date, from or to of a message as text."""
        name_lower = name.lower()

        if name_lower == "subject":
            return message.subject or ""
        if name_lower in ("date", "received"):
            received = message.received
            if not received:
                return ""
            if received.tzinfo is None:
                received = received.replace(tzinfo=timezone.utc)
            return received.astimezone(timezone.utc).isoformat()
        if name_lower == "from":
            return message.sender.address if message.sender else ""
        if name_lower == "to":
            try:
                return ", ".join(r.address for r in message.to if r.address)
            except Exception:
                return ""
        return ""

    def get_body(self, message: Any) -> str:
        """Returns the message body as plain, whitespace-normalized text."""
        body = message.body or ""
        if "<" in body and ">" in body:
            body = re.sub(r"<[^>]+>", " ", body)
        return " ".join(body.split())
