import json
import os
from datetime import datetime

from app.config import TRANSACTIONS_FILE, DATA_DIR

class TransactionStorage:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)

    def load(self):
        if not os.path.exists(TRANSACTIONS_FILE):
            return {
                "last_sync": None,
                "transactions": []
            }

        with open(TRANSACTIONS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    def save(self, data):
        data["last_sync"] = datetime.now().isoformat()

        with open(TRANSACTIONS_FILE, "w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=4
            )

    def get_processed_ids(self, data):
        return {
            transaction["message_id"]
            for transaction in data["transactions"]
            if "message_id" in transaction
        }

    def add_transactions(self, data, transactions):
        data["transactions"].extend(
            transaction.to_dict()
            for transaction in transactions
        )