import re
from datetime import datetime
from O365 import Account
from app.config import OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET, OUTLOOK_SUBJECT, outlook_scopes

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
        and returns all matching messages as a list.

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

        print("Fetching emails")
        
        # 1. Create the base query builder
        builder = inbox.new_query()
        
        # Define our primary subject filter clause
        subject_clause = builder.contains('subject', OUTLOOK_SUBJECT)
        final_query = subject_clause

        # If a dynamic date string is passed, chain them together using chain_and
        if query and "after:" in query:
            try:
                date_part = query.split("after:")[-1].strip()
                formatted_timestamp = datetime.strptime(date_part, "%Y/%m/%d")
                
                # Define the date filter clause
                date_clause = builder.greater_equal('received_date_time', formatted_timestamp)
                
                # Use the exact doc syntax to logically merge both clauses
                final_query = builder.chain_and(subject_clause, date_clause)
                
            except Exception as e:
                print(f"Warning: Could not parse dynamic date filter for Outlook: {e}")

        # 4. Pull results from Microsoft Graph using our combined query
        messages = list(inbox.get_messages(limit=9999, query=final_query))

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