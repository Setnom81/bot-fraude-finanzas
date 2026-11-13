from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pymysql
import pymysql.cursors

from src.config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    LOCAL_TZ,
)

# alert_status values:
#   pending      stored, not scored/alerted yet (retried every cycle)
#   not_needed   scored, low risk
#   sent         high risk, Telegram alert delivered
#   skipped_old  high risk, but too old for an individual alert
#   imported     historical import, never alerted
#   NULL         rows stored before these columns existed
ALERT_COLUMNS = {
    "risk_score": "DECIMAL(5, 2) NULL",
    "is_high_risk": "TINYINT(1) NULL",
    "alert_status": "VARCHAR(20) NULL",
    "alerted_at": "DATETIME NULL",
}

_DATETIME_KEYS = ["transaction_date", "email_date", "processed_at", "created_at", "alerted_at"]


def _to_utc_naive(value):
    """Parses a timestamp and returns it as naive UTC (or None)."""
    if value is None or value == "":
        return None
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    return ts.tz_localize(None)


def _to_naive(value):
    """Parses a wall-clock timestamp (ISO first, then day-first) or None."""
    if value is None or value == "":
        return None
    try:
        return pd.Timestamp(datetime.fromisoformat(str(value))).tz_localize(None)
    except (ValueError, TypeError):
        ts = pd.to_datetime(value, errors="coerce", dayfirst=True)
        return None if pd.isna(ts) else ts.tz_localize(None)


class TransactionStorage:
    """Persistence of transactions and their alert state in MySQL."""

    def __init__(self):
        if not DB_PASSWORD:
            raise RuntimeError("DB_PASSWORD is not set. Add it to src/.env.")

        self.db_config = {
            "host": DB_HOST,
            "port": DB_PORT,
            "user": DB_USER,
            "password": DB_PASSWORD,
            "database": DB_NAME,
            "cursorclass": pymysql.cursors.DictCursor,
            "autocommit": True,
            "charset": "utf8mb4",
        }
        self._create_table_if_not_exists()
        self._add_missing_columns()

    def _get_connection(self):
        return pymysql.connect(**self.db_config)

    def _execute(self, sql, params=None, fetch=False):
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return list(cursor.fetchall()) if fetch else cursor.rowcount
        finally:
            conn.close()

    def _create_table_if_not_exists(self):
        self._execute(
            """
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

                -- Dashboard helper columns (local time)
                hour INT,
                day_of_week INT,
                is_weekend TINYINT(1),

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

    def _add_missing_columns(self):
        """Adds the scoring/alert columns to tables created by older versions."""
        rows = self._execute(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'transactions'",
            (DB_NAME,),
            fetch=True,
        )
        existing = {row["COLUMN_NAME"].lower() for row in rows}
        for name, definition in ALERT_COLUMNS.items():
            if name not in existing:
                self._execute(f"ALTER TABLE transactions ADD COLUMN {name} {definition}")

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def load_transactions(self):
        """Returns every stored transaction as a list of dicts, newest first."""
        transactions = self._execute(
            "SELECT * FROM transactions ORDER BY email_date DESC", fetch=True
        )
        for tx in transactions:
            for key in _DATETIME_KEYS:
                if isinstance(tx.get(key), datetime):
                    tx[key] = tx[key].isoformat()
        return transactions

    def load(self):
        """Compatibility wrapper used by main.py and the dashboard."""
        return {
            "last_sync": datetime.now().isoformat(),
            "transactions": self.load_transactions(),
        }

    def save(self, data):
        """Compatibility no-op: rows are written by add_transactions."""
        data["last_sync"] = datetime.now().isoformat()

    def get_processed_ids(self, data=None):
        """Message IDs already stored."""
        rows = self._execute("SELECT message_id FROM transactions", fetch=True)
        return {row["message_id"] for row in rows if row.get("message_id")}

    def get_pending_ids(self):
        """Message IDs stored but not yet scored/alerted."""
        rows = self._execute(
            "SELECT message_id FROM transactions WHERE alert_status = 'pending'",
            fetch=True,
        )
        return {row["message_id"] for row in rows}

    def get_latest_email_date(self):
        """Arrival time (naive UTC) of the newest stored email, or None."""
        rows = self._execute("SELECT MAX(email_date) AS latest FROM transactions", fetch=True)
        return rows[0]["latest"] if rows else None

    def count_since(self, since_utc):
        """Counts transactions and sent alerts for emails received since a UTC time."""
        rows = self._execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(alert_status = 'sent'), 0) AS alerts "
            "FROM transactions WHERE email_date >= %s",
            (since_utc.strftime("%Y-%m-%d %H:%M:%S"),),
            fetch=True,
        )
        return int(rows[0]["total"]), int(rows[0]["alerts"])

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def add_transactions(self, data, transactions, alert_status="pending"):
        """Inserts parsed transactions, ignoring ones already stored.

        Args:
            data (dict | None): Legacy in-memory structure, updated in place if given.
            transactions (list): Transaction objects or dicts.
            alert_status (str): Initial alert state of the new rows.

        Returns:
            int: Number of rows actually inserted.
        """
        if not transactions:
            return 0

        query = """
        INSERT IGNORE INTO transactions (
            message_id, bank, amount, amount_value, currency, merchant,
            card_last4, transaction_date, authorization, email_from, email_to,
            email_subject, email_date, processed_at, hour, day_of_week, is_weekend,
            alert_status
        ) VALUES (
            %(message_id)s, %(bank)s, %(amount)s, %(amount_value)s, %(currency)s, %(merchant)s,
            %(card_last4)s, %(transaction_date)s, %(authorization)s, %(email_from)s, %(email_to)s,
            %(email_subject)s, %(email_date)s, %(processed_at)s, %(hour)s, %(day_of_week)s, %(is_weekend)s,
            %(alert_status)s
        )
        """
        fmt = "%Y-%m-%d %H:%M:%S"
        local_zone = ZoneInfo(LOCAL_TZ)

        records = []
        for t in transactions:
            item = dict(t.to_dict() if hasattr(t, "to_dict") else t)

            email_dt = _to_utc_naive(item.get("email_date"))
            processed_dt = _to_naive(item.get("processed_at"))
            tx_dt = _to_naive(item.get("transaction_date"))

            # Local purchase time: the bank's own timestamp, else arrival time.
            if tx_dt is not None:
                local_dt = tx_dt
            elif email_dt is not None:
                local_dt = email_dt.tz_localize("UTC").tz_convert(local_zone).tz_localize(None)
            else:
                local_dt = None

            item["email_date"] = email_dt.strftime(fmt) if email_dt is not None else None
            item["processed_at"] = processed_dt.strftime(fmt) if processed_dt is not None else None
            item["transaction_date"] = tx_dt.strftime(fmt) if tx_dt is not None else None
            item["hour"] = local_dt.hour if local_dt is not None else None
            item["day_of_week"] = local_dt.dayofweek if local_dt is not None else None
            item["is_weekend"] = 1 if item["day_of_week"] in (5, 6) else 0
            item["alert_status"] = alert_status
            item.pop("body", None)

            records.append(item)

        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                inserted = cursor.executemany(query, records) or 0
        finally:
            conn.close()

        if data and isinstance(data.get("transactions"), list):
            data["transactions"].extend(records)

        print(f"✅ Se guardaron {inserted} transacciones en la base de datos MySQL.")
        return inserted

    def set_alert_result(self, message_id, risk_score, is_high_risk, alert_status):
        """Stores the scoring outcome and alert state of one transaction."""
        alerted_at = (
            datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if alert_status == "sent" else None
        )
        self._execute(
            "UPDATE transactions SET risk_score = %s, is_high_risk = %s, "
            "alert_status = %s, alerted_at = %s WHERE message_id = %s",
            (
                None if risk_score is None else round(float(risk_score), 2),
                None if is_high_risk is None else int(bool(is_high_risk)),
                alert_status,
                alerted_at,
                message_id,
            ),
        )
