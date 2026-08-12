from datetime import datetime
import os

# Imports application configuration constants.
from app.config import (
    DEFAULT_START_DATE, 
    QUERY_TEMPLATE, 
    OUTLOOK_CLIENT_ID, 
    OUTLOOK_CLIENT_SECRET
)

# Imports the clients responsible for interacting with the email APIs.
from app.gmail_client import GmailClient
from app.outlook_client import OutlookClient  # Your new Outlook wrapper

# Imports the parser responsible for extracting transaction data from BAC notification emails.
from app.parser import BacParser

# Imports the storage layer used to persist processed transactions and synchronization metadata.
from app.storage import TransactionStorage


def iso_to_gmail_date(value):
    """
    Converts an ISO 8601 datetime string into the date format
    expected by Gmail search queries.
    """
    if not value:
        return DEFAULT_START_DATE

    dt = datetime.fromisoformat(value)
    return dt.strftime("%Y/%m/%d")


def get_available_clients():
    """
    Inspects environment configurations and safely returns 
    whichever email clients have valid credentials available.
    """
    clients = {}

    # Check & Load Outlook
    if OUTLOOK_CLIENT_ID and OUTLOOK_CLIENT_SECRET:
        print("Outlook credentials found. Initializing OutlookClient...")
        try:
            clients['outlook'] = OutlookClient()
        except Exception as e:
            print(f"Failed to initialize OutlookClient: {e}")
    else:
        print("Outlook credentials missing in .env. Skipping Outlook.")

    # Check & Load Gmail. We check if the token file exists before calling GmailClient to prevent crashes.
    gmail_token_exists = os.path.exists('data/token.json') 
    gmail_credentials_exists = os.path.exists('data/credentials.json')

    if gmail_token_exists or gmail_credentials_exists:
        print("Gmail credentials/token found. Initializing GmailClient...")
        try:
            clients['gmail'] = GmailClient()
        except Exception as e:
            print(f"Failed to initialize GmailClient: {e}")
    else:
        print("Gmail token.json or credentials.json not found. Skipping Gmail.")

    return clients


def main():
    """
    Main application entry point supporting dynamic multi-provider execution.
    """
    # Initialize client factory map
    active_clients = get_available_clients()
    if not active_clients:
        print("Error: No email service credentials could be verified.")
        return

    # Loads the local transaction database.
    storage = TransactionStorage()
    data = storage.load()

    # Determines the starting date for searching messages.
    start_date = iso_to_gmail_date(data.get("last_sync"))
    query = QUERY_TEMPLATE.format(start_date=start_date)

    parser = BacParser()
    processed_ids = storage.get_processed_ids(data)
    new_transactions = []

    # Iterate through whatever clients were successfully authenticated
    for provider_name, client in active_clients.items():
        print(f"\n--- Processing Inbox: {provider_name.upper()} ---")
        print(f"Searching with query: {query}")

        # Searches for matching transaction emails.
        messages = client.search_messages(query)
        
        # Processes each matching message.
        for item in messages:
            # Gmail uses dict layout item['id'], O365 uses custom object attributes
            # We abstract this check depending on the provider type
            if provider_name == 'gmail':
                message_id = item["id"]
            else:
                message_id = item.object_id  # O365 message identification property

            # Skips emails that have already been processed.
            if message_id in processed_ids:
                print(f"Skipping duplicate message: {message_id}")
                continue

            # Retrieves the complete message payload
            message = client.get_message(message_id)

            # Extract headers and body uniformly using our class wrappers
            if provider_name == 'gmail':
                payload = message.get("payload", {})
                headers = payload.get("headers", [])
                body = client.get_body(payload)
            else:
                # Pass the native message object as 'headers'.
                headers = message 
                body = client.get_body(message)

            # Parses the email into a uniform transaction object.
            transaction = parser.parse(
                message_id=message_id,
                headers=headers,
                body=body,
                gmail_client=client
            )

            new_transactions.append(transaction)
            print(f"Transaction detected: {transaction.amount} - {transaction.merchant}")

    # Persist all newly discovered entries
    if new_transactions:
        storage.add_transactions(data, new_transactions)
        storage.save(data)


if __name__ == "__main__":
    main()