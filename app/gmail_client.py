import base64
import re

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.config import SCOPES, TOKEN_FILE

class GmailClient:
    def __init__(self):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        self.service = build("gmail", "v1", credentials=creds)

    def search_messages(self, query):
        messages = []
        page_token = None

        while True:
            response = self.service.users().messages().list(
                userId="me",
                q=query,
                pageToken=page_token
            ).execute()

            messages.extend(response.get("messages", []))
            page_token = response.get("nextPageToken")

            if not page_token:
                break

        return messages

    def get_message(self, message_id):
        return self.service.users().messages().get(
            userId="me",
            id=message_id,
            format="full"
        ).execute()

    def get_header(self, headers, name):
        return next(
            (
                header["value"]
                for header in headers
                if header["name"].lower() == name.lower()
            ),
            ""
        )

    def get_body(self, payload):
        body = ""

        if "parts" in payload:
            for part in payload["parts"]:
                mime = part.get("mimeType", "")

                if mime == "text/plain":
                    data = part.get("body", {}).get("data")
                    if data:
                        body += self.decode_base64(data)

                elif mime == "text/html" and not body:
                    data = part.get("body", {}).get("data")
                    if data:
                        html = self.decode_base64(data)
                        body += re.sub(r"<[^>]+>", " ", html)

                elif "parts" in part:
                    body += self.get_body(part)
        else:
            data = payload.get("body", {}).get("data")
            if data:
                body += self.decode_base64(data)

        return " ".join(body.split())

    @staticmethod
    def decode_base64(data):
        return base64.urlsafe_b64decode(data).decode(
            "utf-8",
            errors="ignore"
        )