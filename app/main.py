from datetime import datetime

# Imports application configuration constants.
from app.config import DEFAULT_START_DATE, QUERY_TEMPLATE

# Imports the Gmail client responsible for interacting with the Gmail API.
from app.gmail_client import GmailClient

# Imports the parser responsible for extracting transaction data
# from BAC notification emails.
from app.parser import BacParser

# Imports the storage layer used to persist processed transactions
# and synchronization metadata.
from app.storage import TransactionStorage


def iso_to_gmail_date(value):
    """
    Converts an ISO 8601 datetime string into the date format
    expected by Gmail search queries.

    If no value is provided, the application's default start date
    is returned.

    Args:
        value (str | None): ISO 8601 datetime string.

    Returns:
        str: Date formatted as YYYY/MM/DD.
    """
    if not value:
        return DEFAULT_START_DATE

    dt = datetime.fromisoformat(value)
    return dt.strftime("%Y/%m/%d")


def main():
    """
    Main application entry point.

    Workflow:
        1. Load previously stored transaction data.
        2. Determine the last synchronization date.
        3. Search Gmail for new transaction notification emails.
        4. Parse each unprocessed email into a transaction object.
        5. Save newly discovered transactions.
    """

    # Loads the local transaction database.
    storage = TransactionStorage()
    data = storage.load()

    # Determines the starting date for the Gmail search.
    # If no previous synchronization exists, the default date is used.
    start_date = iso_to_gmail_date(data.get("last_sync"))

    # Builds the Gmail search query using the configured template.
    query = QUERY_TEMPLATE.format(start_date=start_date)

    print("Searching Gmail with query:")
    print(query)

    # Initializes the Gmail API client and the transaction parser.
    gmail = GmailClient()
    parser = BacParser()

    # Retrieves the IDs of previously processed messages to avoid duplicates.
    processed_ids = storage.get_processed_ids(data)

    # Searches Gmail for matching transaction emails.
    messages = gmail.search_messages(query)

    print(f"Emails found: {len(messages)}")

    # Stores newly discovered transactions before persisting them.
    new_transactions = []

    # Processes each matching Gmail message.
    for item in messages:
        message_id = item["id"]

        # Skips emails that have already been processed.
        if message_id in processed_ids:
            print(f"Skipping duplicate message: {message_id}")
            continue

        # Retrieves the complete Gmail message.
        message = gmail.get_message(message_id)

        payload = message.get("payload", {})
        headers = payload.get("headers", [])

        # Extracts and cleans the email body.
        body = gmail.get_body(payload)

        # Parses the email into a transaction object.
        transaction = parser.parse(
            message_id=message_id,
            headers=headers,
            body=body,
            gmail_client=gmail
        )

        # Adds the transaction to the list of new records.
        new_transactions.append(transaction)

        print(
            f"Transaction detected: "
            f"{transaction.amount} - {transaction.merchant}"
        )

    # Persists the newly parsed transactions.
    storage.add_transactions(data, new_transactions)
    storage.save(data)

    # Displays a summary of the synchronization.
    print(f"New transactions: {len(new_transactions)}")
    print(f"Total stored transactions: {len(data['transactions'])}")


# Executes the application only when this file is run directly.
# This prevents the main workflow from running if the module
# is imported by another script.
if __name__ == "__main__":
    main()