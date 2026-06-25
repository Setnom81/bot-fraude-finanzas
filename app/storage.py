import json
import os
from datetime import datetime

# Imports application configuration constants.
from app.config import TRANSACTIONS_FILE, DATA_DIR


class TransactionStorage:
    """
    Handles persistence of transaction data.

    This class is responsible for:
        - Loading stored transactions.
        - Saving transaction data to disk.
        - Tracking the last synchronization timestamp.
        - Identifying previously processed Gmail messages.
    """

    def __init__(self):
        """
        Ensures that the application's data directory exists
        before any file operations are performed.
        """
        os.makedirs(DATA_DIR, exist_ok=True)

    def load(self):
        """
        Loads the transaction database from disk.

        If the storage file does not exist, a new empty
        data structure is returned.

        Returns:
            dict: Stored transaction data.
        """
        if not os.path.exists(TRANSACTIONS_FILE):
            return {
                "last_sync": None,
                "transactions": []
            }

        with open(TRANSACTIONS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    def save(self, data):
        """
        Saves the transaction database to disk.

        The last synchronization timestamp is updated before
        writing the file.

        Args:
            data (dict): Transaction data to persist.
        """
        # Updates the synchronization timestamp to indicate
        # when the latest save operation occurred.
        data["last_sync"] = datetime.now().isoformat()

        with open(TRANSACTIONS_FILE, "w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=4
            )

    def get_processed_ids(self, data):
        """
        Retrieves the set of Gmail message IDs that have already
        been processed.

        This is used to prevent duplicate transaction imports.

        Args:
            data (dict): Stored transaction data.

        Returns:
            set[str]: Processed Gmail message IDs.
        """
        return {
            transaction["message_id"]
            for transaction in data["transactions"]
            if "message_id" in transaction
        }

    def add_transactions(self, data, transactions):
        """
        Appends newly parsed transactions to the existing
        transaction collection.

        Args:
            data (dict): Current transaction data.
            transactions (list[Transaction]): Transactions
                to be stored.
        """
        data["transactions"].extend(
            transaction.to_dict()
            for transaction in transactions
        )