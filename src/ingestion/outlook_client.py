from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Any, Dict, List, Optional

from O365 import Account
from src.config import (
    OUTLOOK_CLIENT_ID,
    OUTLOOK_CLIENT_SECRET,
    OUTLOOK_SUBJECT,
    outlook_scopes,
)


class OutlookClient:
    """Wrapper around the Microsoft Graph API via O365 library.

    Provides interface methods for authenticating, querying inbox messages,
    extracting headers/bodies, and parsing recent financial transaction payloads.
    """

    def __init__(self) -> None:
        """Initializes the O365 Account instance and handles OAuth2 token authentication flow."""
        if not OUTLOOK_CLIENT_ID or not OUTLOOK_CLIENT_SECRET:
            logging.error(
                "Initialization aborted: OUTLOOK_CLIENT_ID or OUTLOOK_CLIENT_SECRET is missing."
            )
            self.account: Optional[Account] = None
            return

        credentials = (OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET)
        self.account = Account(credentials)

        if not self.account.is_authenticated:
            logging.info("Initiating OAuth2 authorization flow...")
            self.account.authenticate(scopes=outlook_scopes)
            logging.info(
                "OAuth2 authentication successful. Session token cached locally."
            )
        else:
            logging.info(
                "OAuth2 session successfully validated using cached credentials."
            )

    def search_messages(self, query: Optional[str] = None) -> List[Any]:
        """Queries the Outlook inbox using an OData filter derived from input search criteria.

        Args:
            query (Optional[str]): Search query containing optional 'after:YYYY/MM/DD' date bounds.

        Returns:
            List[Any]: List of O365 Message objects matching the specified OData filter parameters.
        """
        if not self.account:
            logging.error(
                "Search execution failed: Account instance is uninitialized."
            )
            return []

        mailbox = self.account.mailbox()
        inbox = mailbox.inbox_folder()

        logging.info("Querying Microsoft Graph API inbox endpoint...")

        filter_clauses = [f"contains(subject, '{OUTLOOK_SUBJECT}')"]

        if query and "after:" in query:
            try:
                date_part = query.split("after:")[-1].strip().split()[0]
                dt = datetime.strptime(date_part, "%Y/%m/%d").replace(
                    tzinfo=timezone.utc
                )

                # Format to ISO 8601 UTC string (e.g., 2026-08-12T00:00:00Z)
                iso_date = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                filter_clauses.append(f"receivedDateTime ge {iso_date}")
            except Exception as e:
                logging.warning(
                    f"Failed to parse dynamic date parameter into OData filter: {e}"
                )

        odata_filter = " and ".join(filter_clauses)
        messages = list(inbox.get_messages(limit=9999, query=odata_filter))

        for message in messages:
            logging.debug(f"Retrieved email payload subject: {message.subject}")

        return messages

    def get_message(self, message_id: str) -> Optional[Any]:
        """Fetches a specific Outlook message object by its unique object ID.

        Args:
            message_id (str): Unique Microsoft Graph API object identifier for the target message.

        Returns:
            Optional[Any]: Complete O365 Message instance if located, otherwise None.
        """
        if not self.account:
            logging.error(
                "Message retrieval failed: Account instance is uninitialized."
            )
            return None

        mailbox = self.account.mailbox()
        return mailbox.get_message(message_id)

    def get_header(self, message: Any, name: str) -> str:
        """Extracts standard email header metadata from an O365 Message entity.

        Args:
            message (Any): O365 Message object instance.
            name (str): Target header attribute identifier (e.g., 'subject', 'date', 'from').

        Returns:
            str: Extracted metadata header string value, or empty string if not present.
        """
        name_lower = name.lower()

        if name_lower == "subject":
            return message.subject or ""
        elif name_lower in ("date", "received"):
            return str(message.received) if message.received else ""
        elif name_lower == "from":
            return message.sender.address if message.sender else ""

        return ""

    def get_body(self, message: Any) -> str:
        """Extracts, strips HTML tags from, and normalizes the body text of an O365 Message object.

        Args:
            message (Any): O365 Message object instance.

        Returns:
            str: Sanitized and whitespace-normalized plaintext message body string.
        """
        body = message.body or ""

        # Strip inline HTML markup if detected in body payload
        if "<" in body and ">" in body:
            body = re.sub(r"<[^>]+>", " ", body)

        # Normalize redundant whitespace and line breaks
        return " ".join(body.split())

    def fetch_recent_transactions(
        self, minutes_back: int = 15
    ) -> List[Dict[str, Any]]:
        """Retrieves transaction notification emails received within the designated temporal window.

        Args:
            minutes_back (int): Trailing time window length in minutes to query backwards from UTC now.

        Returns:
            List[Dict[str, Any]]: List of parsed email dictionaries containing ID, subject, sender,
                timestamp, and plain text body.
        """
        if not self.account:
            logging.error(
                "Transaction fetch failed: Account instance is uninitialized."
            )
            return []

        mailbox = self.account.mailbox()
        inbox = mailbox.inbox_folder()

        # 1. Compute UTC timestamp cutoff for OData filter window
        time_threshold = datetime.now(timezone.utc) - timedelta(
            minutes=minutes_back
        )
        iso_date = time_threshold.strftime("%Y-%m-%dT%H:%M:%SZ")

        # 2. Construct OData filter query clause: Subject matching AND receivedDateTime threshold
        filter_clauses = [
            f"contains(subject, '{OUTLOOK_SUBJECT}')",
            f"receivedDateTime ge {iso_date}",
        ]
        odata_filter = " and ".join(filter_clauses)

        logging.info(
            f"Querying transaction email notifications received since: {iso_date} UTC..."
        )

        # 3. Execute Microsoft Graph API request
        messages = list(inbox.get_messages(limit=50, query=odata_filter))

        parsed_emails: List[Dict[str, Any]] = []
        for msg in messages:
            parsed_emails.append(
                {
                    "id": msg.object_id,
                    "subject": self.get_header(msg, "subject"),
                    "from": self.get_header(msg, "from"),
                    "date": str(msg.received),
                    "body": self.get_body(msg),
                }
            )

        return parsed_emails