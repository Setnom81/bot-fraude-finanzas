import os
import pymysql
import pymysql.cursors
from datetime import datetime
import pandas as pd

# Imports application configuration constants.
# Asegúrate de agregar las constantes de conexión DB a tu config.py
from src.config import (
    DB_HOST,
    DB_PORT,
    DB_USER,
    DB_PASSWORD,
    DB_NAME
)


class TransactionStorage:
    """
    Handles persistence of transaction data into a MySQL database.

    This class is responsible for:
        - Connecting to MySQL and ensuring schema existence.
        - Fetching stored transactions and processed IDs.
        - Inserting new transactions and automatically computing ML features.
    """

    def __init__(self):
        """
        Initializes the database connection parameters and ensures
        that the required MySQL table exists.
        """
        self.db_config = {
            "host": DB_HOST,
            "port": DB_PORT,
            "user": DB_USER,
            "password": DB_PASSWORD,
            "database": DB_NAME,
            "cursorclass": pymysql.cursors.DictCursor,
            "autocommit": True
        }
        self._create_table_if_not_exists()

    def _get_connection(self):
        """Establishes and returns a new connection to MySQL."""
        return pymysql.connect(**self.db_config)

    def _create_table_if_not_exists(self):
        """Creates the transactions table if it does not already exist."""
        table_sql = """
        CREATE TABLE IF NOT EXISTS transactions (
            message_id VARCHAR(255) PRIMARY KEY,
            bank VARCHAR(50),
            amount VARCHAR(50),
            amount_value DECIMAL(12, 2),
            currency VARCHAR(10),
            merchant VARCHAR(255),
            card_last4 VARCHAR(10),
            transaction_date DATETIME NULL,
            authorization VARCHAR(50),
            email_from VARCHAR(255),
            email_to VARCHAR(255),
            email_subject VARCHAR(255),
            email_date DATETIME NULL,
            processed_at DATETIME NULL,
            
            -- ML and Dashboard Features
            hour INT,
            day_of_week INT,
            is_weekend TINYINT(1),
            
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(table_sql)
        finally:
            conn.close()

    def load(self):
        """
        Loads all transactions from the MySQL database.

        Returns:
            dict: Data structure containing 'last_sync' and list of transactions.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM transactions ORDER BY email_date DESC")
                transactions = list(cursor.fetchall())
                
                for tx in transactions:
                    for key in ["transaction_date", "email_date", "processed_at", "created_at"]:
                        if tx.get(key) and isinstance(tx[key], datetime):
                            tx[key] = tx[key].isoformat()

                return {
                    "last_sync": datetime.now().isoformat(),
                    "transactions": transactions
                }
        finally:
            conn.close()

    def save(self, data):
        """
        Updates synchronization timestamp.
        Since add_transactions inserts directly into MySQL, this acts as a 
        compatibility method for main.py.
        """
        data["last_sync"] = datetime.now().isoformat()

    def get_processed_ids(self, data=None):
        """
        Retrieves the set of message IDs already stored in MySQL.
        Queries the database directly for optimal performance.

        Args:
            data (dict, optional): Kept for backward compatibility.

        Returns:
            set[str]: Processed message IDs.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT message_id FROM transactions")
                rows = cursor.fetchall()
                return {row["message_id"] for row in rows if row.get("message_id")}
        finally:
            conn.close()

    def add_transactions(self, data, transactions):
        """
        Inserts newly parsed transactions into MySQL, generating
        time-based features automatically and ignoring duplicates.

        Args:
            data (dict): Current transaction data dict (updated in-place for main.py).
            transactions (list[Transaction]): List of Transaction objects to persist.
        """
        if not transactions:
            return

        query = """
        INSERT IGNORE INTO transactions (
            message_id, bank, amount, amount_value, currency, merchant,
            card_last4, transaction_date, authorization, email_from, email_to,
            email_subject, email_date, processed_at, hour, day_of_week, is_weekend
        ) VALUES (
            %(message_id)s, %(bank)s, %(amount)s, %(amount_value)s, %(currency)s, %(merchant)s,
            %(card_last4)s, %(transaction_date)s, %(authorization)s, %(email_from)s, %(email_to)s,
            %(email_subject)s, %(email_date)s, %(processed_at)s, %(hour)s, %(day_of_week)s, %(is_weekend)s
        )
        """

        records = []
        for t in transactions:
            item = t.to_dict() if hasattr(t, "to_dict") else t
            
            # Parse Dates
            email_dt = pd.to_datetime(item.get("email_date")) if item.get("email_date") else None
            processed_dt = pd.to_datetime(item.get("processed_at")) if item.get("processed_at") else None
            tx_dt = pd.to_datetime(item.get("transaction_date")) if item.get("transaction_date") else None

            # Calculate ML Features using email_date as fallback
            ref_dt = tx_dt if pd.notnull(tx_dt) else email_dt
            
            item["email_date"] = email_dt.strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(email_dt) else None
            item["processed_at"] = processed_dt.strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(processed_dt) else None
            item["transaction_date"] = tx_dt.strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(tx_dt) else None

            item["hour"] = ref_dt.hour if pd.notnull(ref_dt) else None
            item["day_of_week"] = ref_dt.dayofweek if pd.notnull(ref_dt) else None
            item["is_weekend"] = 1 if (item["day_of_week"] is not None and item["day_of_week"] in [5, 6]) else 0

            records.append(item)

        # Execute Batch Insert in MySQL
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.executemany(query, records)
            
            # Keep the in-memory 'data' structure synced for main.py
            if data and "transactions" in data:
                if not isinstance(data["transactions"], list):
                    data["transactions"] = list(data["transactions"])
                
                data["transactions"].extend(records)
                
            print(f"✅ Se guardaron {len(records)} transacciones en la base de datos MySQL.")
        finally:
            conn.close()