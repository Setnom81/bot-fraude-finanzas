import re
from datetime import datetime, timezone
from O365 import Account
from config import OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET, OUTLOOK_SUBJECT, outlook_scopes

class OutlookClient:
    """
    Wrapper around the Outlook API that provides helper methods for
    searching messages, retrieving email content, and extracting
    useful information from Outlook responses.
    """
        
    def __init__(self):
        # Stop initialization early if keys are missing
        if not OUTLOOK_CLIENT_ID or not OUTLOOK_CLIENT_SECRET:
            print("Missing credentials in env file")
            self.account = None
            return
            
        # Build the Account object
        credentials = (OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET)
        self.account = Account(credentials)

        # Check and verify authentication status
        if not self.account.is_authenticated:
            print("--- FIRST TIME LOGIN FLOW ---")
            # This will print the URL to your console
            self.account.authenticate(scopes=outlook_scopes)
            print("\nAuthentication successful! A token has been saved locally.")
        else:
            print("Already authenticated via saved token.")

    def search_messages(self, query=None):
        """
        Searches Outlook using the provided query string, translates date parameters,
        and returns all matching messages as a list using an OData filter string.

        Args:
            query (str): The Gmail-formatted search query string (e.g., contains 'after:YYYY/MM/DD').

        Returns:
            list: A list of O365 Message objects.
        """
        if not self.account:
            print("Cannot search messages: Missing account configuration.")
            return []

        mailbox = self.account.mailbox()
        inbox = mailbox.inbox_folder()

        print("Fetching emails...")

        # 1. Crear cláusula base para el asunto
        filter_clauses = [f"contains(subject, '{OUTLOOK_SUBJECT}')"]

        # 2. Parsear el filtro 'after:' si viene en el query
        if query and "after:" in query:
            try:
                date_part = query.split("after:")[-1].strip().split()[0]
                dt = datetime.strptime(date_part, "%Y/%m/%d").replace(tzinfo=timezone.utc)
                
                # Formatear a estándar ISO 8601 UTC (ejemplo: 2026-08-12T00:00:00Z)
                iso_date = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                filter_clauses.append(f"receivedDateTime ge {iso_date}")
            except Exception as e:
                print(f"Warning: Could not parse dynamic date filter for Outlook: {e}")

        # 3. Unir los filtros con 'and' para la sintaxis OData
        odata_filter = " and ".join(filter_clauses)

        # 4. Consultar Microsoft Graph directamente con la cadena OData
        messages = list(inbox.get_messages(limit=9999, query=odata_filter))

        for message in messages:
            print(f'Found: {message.subject}')

        return messages
    
    def get_message(self, message_id):
        """
        Retrieves the full content of an Outlook message using its unique ID.

        Args:
            message_id (str): Outlook object message ID.

        Returns:
            Message: Complete O365 Message object.
        """
        mailbox = self.account.mailbox()
        # Retrieves the specific message directly from Microsoft Graph API
        return mailbox.get_message(message_id)

    def get_header(self, message, name):
        """
        Retrieves common metadata properties from an Outlook message object.
        Because O365 parses properties natively, standard headseners are mapped directly.

        Args:
            message (Message): The O365 Message object.
            name (str): Property name (e.g., "Subject", "Date", "From").

        Returns:
            str: Property value string, or an empty string if not found.
        """
        name_lower = name.lower()
        
        if name_lower == "subject":
            return message.subject or ""
        elif name_lower == "date" or name_lower == "received":
            return str(message.received) if message.received else ""
        elif name_lower == "from":
            return message.sender.address if message.sender else ""
        
        # Fallback if you explicitly need access to custom raw network headers
        return ""

    def get_body(self, message):
        """
        Extracts and cleans the body from an Outlook message object.
        O365 gives us the text natively, meaning base64 decoding and multipart 
        unrolling are completely bypassed.

        Args:
            message (Message): The O365 Message object.

        Returns:
            str: Cleaned and normalized text body.
        """
        # O365 populates body with text/plain if available, otherwise text/html
        body = message.body or ""
        
        # Check if the body contains HTML tags to clean them up (replicates your Gmail logic)
        if "<" in body and ">" in body:
            body = re.sub(r"<[^>]+>", " ", body)

        # Normalizes whitespace before returning
        return " ".join(body.split())