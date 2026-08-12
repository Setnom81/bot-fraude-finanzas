from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Any, Dict, List

from src.config import QUERY_TEMPLATE
from src.database.storage import TransactionStorage
from src.ingestion.outlook_client import OutlookClient
from src.ingestion.parsers.bac_parser import BacParser
from src.ml.inference import process_and_alert_new_transactions

# Configure root logger format and console handler
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)


class EmailAlertService:
    """Daemon service that periodically polls Outlook inbox for incoming transaction emails

    within a dynamic lookback window, parses entity attributes, persists records to MySQL,
    and evaluates real-time risk scores for instant alerting.
    """

    def __init__(
        self, poll_interval_seconds: int = 120, lookback_minutes: int = 5
    ) -> None:
        """Initializes the EmailAlertService instance and service dependencies.

        Args:
            poll_interval_seconds (int): Execution sleep duration between polling cycles in seconds.
            lookback_minutes (int): Temporal lookback window threshold in minutes for email filtering.
        """
        self.poll_interval = poll_interval_seconds
        self.lookback_minutes = lookback_minutes
        self.storage = TransactionStorage()
        self.outlook_client = OutlookClient()
        self.parser = BacParser()
        self.is_running = True

    def run_check_cycle(self) -> None:
        """Executes a single polling iteration to query, deduplicate, parse, persist,

        and evaluate incoming transaction email notifications.
        """
        logging.info(
            f"Querying transaction email notifications received within the last {self.lookback_minutes} minutes..."
        )

        try:
            data = self.storage.load()
            processed_ids = self.storage.get_processed_ids(data)

            # 1. Compute exact UTC cutoff timestamp based on configured lookback window
            now_utc = datetime.now(timezone.utc)
            time_threshold = now_utc - timedelta(minutes=self.lookback_minutes)

            # 2. Append date boundary filter to optimize Graph API search payload
            today_str = now_utc.strftime("%Y/%m/%d")
            query_with_date = f"{QUERY_TEMPLATE} after:{today_str}"

            messages = self.outlook_client.search_messages(query_with_date)

            if not messages:
                logging.info(
                    "No matching email messages found. Entering idle sleep cycle..."
                )
                return

            new_transactions: List[Any] = []

            for item in messages:
                message_id = item.object_id

                # Deduplication check against persistent storage
                if message_id in processed_ids:
                    continue

                # 3. Validate message timestamp against lookback cutoff
                msg_date = getattr(item, "received", None) or getattr(
                    item, "created", None
                )
                if msg_date:
                    # Ensure timestamp object is timezone-aware (UTC)
                    if msg_date.tzinfo is None:
                        msg_date = msg_date.replace(tzinfo=timezone.utc)

                    # Skip messages received prior to lookback cutoff threshold
                    if msg_date < time_threshold:
                        continue

                # Retrieve full message body payload for valid candidate emails
                message = self.outlook_client.get_message(message_id)
                body = self.outlook_client.get_body(message)

                transaction = self.parser.parse(
                    message_id=message_id,
                    headers=message,
                    body=body,
                    gmail_client=self.outlook_client,
                )

                new_transactions.append(transaction)
                currency_str = getattr(transaction, "currency", "CRC")
                logging.info(
                    f"Recent transaction detected: {currency_str} {transaction.amount} - {transaction.merchant}"
                )

            if not new_transactions:
                logging.info(
                    f"No new unprocessed transactions identified within the {self.lookback_minutes}-minute window."
                )
                return

            # Persist transactions to database and trigger hybrid ML risk evaluation
            self.storage.add_transactions(data, new_transactions)
            self.storage.save(data)
            logging.info(
                f"Successfully persisted {len(new_transactions)} new transaction record(s) to storage."
            )

            process_and_alert_new_transactions(new_transactions)

        except Exception as e:
            logging.error(
                f"Execution error encountered during daemon check cycle: {e}",
                exc_info=True,
            )

    def start(self) -> None:
        """Initiates the continuous polling execution loop for real-time transaction monitoring."""
        logging.info(
            f"Email Alert Daemon activated. Polling interval: {self.poll_interval}s, "
            f"Lookback window: {self.lookback_minutes}m."
        )
        try:
            while self.is_running:
                self.run_check_cycle()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            logging.info(
                "Gracefully shutting down email monitoring daemon service..."
            )


if __name__ == "__main__":
    service = EmailAlertService(
        poll_interval_seconds=120, lookback_minutes=5
    )
    service.start()