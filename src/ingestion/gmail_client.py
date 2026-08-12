import base64
import re

# Imports the Credentials class used to authenticate requests to the Gmail API.
from google.oauth2.credentials import Credentials

# Imports the Google API client builder used to create a Gmail service instance.
from googleapiclient.discovery import build

# Imports the application's Gmail API scopes and the location of the
# stored OAuth token.
from src.config import SCOPES, TOKEN_FILE


class GmailClient:
    """
    Wrapper around the Gmail API that provides helper methods for
    searching messages, retrieving email content, and extracting
    useful information from Gmail responses.
    """

    def __init__(self):
        # Loads the user's OAuth credentials from the saved token file.
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

        # Creates an authenticated Gmail API service client.
        self.service = build("gmail", "v1", credentials=creds)

    def search_messages(self, query):
        """
        Searches Gmail using the provided query and returns all matching
        messages, automatically handling pagination.

        Args:
            query (str): Gmail search query.

        Returns:
            list: A list of message metadata dictionaries.
        """
        messages = []
        page_token = None

        while True:
            # Requests a page of matching messages.
            response = self.service.users().messages().list(
                userId="me",
                q=query,
                pageToken=page_token
            ).execute()

            # Adds the current page of messages to the result list.
            messages.extend(response.get("messages", []))

            # Retrieves the token for the next page, if one exists.
            page_token = response.get("nextPageToken")

            # Stops when there are no more pages.
            if not page_token:
                break

        return messages

    def get_message(self, message_id):
        """
        Retrieves the full content of a Gmail message.

        Args:
            message_id (str): Gmail message ID.

        Returns:
            dict: Complete Gmail message object.
        """
        return self.service.users().messages().get(
            userId="me",
            id=message_id,
            format="full"
        ).execute()

    def get_header(self, headers, name):
        """
        Retrieves the value of a specific email header.

        Args:
            headers (list): List of Gmail message headers.
            name (str): Header name (e.g., "Subject", "Date", "From").

        Returns:
            str: Header value, or an empty string if not found.
        """
        return next(
            (
                header["value"]
                for header in headers
                if header["name"].lower() == name.lower()
            ),
            ""
        )

    def get_body(self, payload):
        """
        Extracts the email body from a Gmail message payload.

        The method:
        - Prefers plain text when available.
        - Falls back to HTML if necessary.
        - Removes HTML tags.
        - Recursively processes multipart messages.

        Args:
            payload (dict): Gmail message payload.

        Returns:
            str: Cleaned email body.
        """
        body = ""

        # Handles multipart emails.
        if "parts" in payload:
            for part in payload["parts"]:
                mime = part.get("mimeType", "")

                # Extracts plain text content.
                if mime == "text/plain":
                    data = part.get("body", {}).get("data")
                    if data:
                        body += self.decode_base64(data)

                # Falls back to HTML if plain text is unavailable.
                elif mime == "text/html" and not body:
                    data = part.get("body", {}).get("data")
                    if data:
                        html = self.decode_base64(data)

                        # Removes HTML tags to obtain readable text.
                        body += re.sub(r"<[^>]+>", " ", html)

                # Recursively processes nested multipart sections.
                elif "parts" in part:
                    body += self.get_body(part)

        # Handles single-part emails.
        else:
            data = payload.get("body", {}).get("data")
            if data:
                body += self.decode_base64(data)

        # Normalizes whitespace before returning.
        return " ".join(body.split())

    @staticmethod
    def decode_base64(data):
        """
        Decodes a URL-safe Base64 encoded string used by the Gmail API.

        Args:
            data (str): Base64 encoded string.

        Returns:
            str: Decoded UTF-8 text.
        """
        return base64.urlsafe_b64decode(data).decode(
            "utf-8",
            errors="ignore"
        )