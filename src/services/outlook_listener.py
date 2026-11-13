from datetime import datetime, timedelta, timezone
import html
import logging
import time
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from src.config import (
    ALERT_MAX_AGE_HOURS,
    ALLOWED_SENDERS,
    FAILURE_ALERT_AFTER,
    FAILURE_REMINDER_HOURS,
    HEARTBEAT_HOUR,
    INITIAL_LOOKBACK_DAYS,
    LOCAL_TZ,
    POLL_INTERVAL_SECONDS,
)

# Each cycle re-reads this much before the previous cycle's start, so an email
# that reaches the mailbox slightly late is still seen. Duplicates are skipped.
OVERLAP = timedelta(minutes=15)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmailAlertService:
    """Polls the Outlook inbox for bank notifications, stores them, scores them
    and sends a Telegram alert for the suspicious ones.

    A transaction is stored as 'pending' and only leaves that state once it has
    been scored and, if it is high risk, its alert was actually delivered. So a
    crash, a Telegram outage or a scoring error delays an alert but never drops it.
    Emails that arrived while the service was not running are picked up on the
    next cycle, because each cycle starts from where the last successful one ended.
    """

    def __init__(
        self,
        poll_interval_seconds: int = POLL_INTERVAL_SECONDS,
        storage: Any = None,
        client_factory: Optional[Callable[[], Any]] = None,
        parser: Any = None,
        scorer: Optional[Callable[[List[Dict[str, Any]], set], List[Dict[str, Any]]]] = None,
        send_alert: Optional[Callable[[Dict[str, Any]], bool]] = None,
        send_message: Optional[Callable[[str], bool]] = None,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        # Imports are local so tests can inject fakes without MySQL/O365/sklearn.
        if storage is None:
            from src.database.storage import TransactionStorage
            storage = TransactionStorage()
        if client_factory is None:
            from src.ingestion.outlook_client import OutlookClient
            client_factory = OutlookClient
        if parser is None:
            from src.ingestion.parsers.bac_parser import BacParser
            parser = BacParser()
        if scorer is None:
            from src.ml.inference import score_transactions
            scorer = score_transactions
        if send_alert is None or send_message is None:
            from src.alerts import telegram
            send_alert = send_alert or telegram.send_telegram_alert
            send_message = send_message or telegram.send_telegram_message

        self.poll_interval = poll_interval_seconds
        self.storage = storage
        self.client_factory = client_factory
        self.parser = parser
        self.scorer = scorer
        self.send_alert = send_alert
        self.send_message = send_message
        self.now = now

        self.client: Any = None
        self.since: Optional[datetime] = None
        self.is_running = True

        self.consecutive_failures = 0
        self.first_failure_at: Optional[datetime] = None
        self.last_failure_alert_at: Optional[datetime] = None
        self.startup_reported = False
        self.last_cycle_local_date = None
        self.reported_problem_ids: set = set()

    # ------------------------------------------------------------------
    # One polling cycle
    # ------------------------------------------------------------------

    def _initial_since(self) -> datetime:
        """Where to start reading: just before the newest stored email."""
        latest = self.storage.get_latest_email_date()
        if latest is None:
            return self.now() - timedelta(days=INITIAL_LOOKBACK_DAYS)
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        return latest - OVERLAP

    def run_check_cycle(self) -> Dict[str, int]:
        """Fetches, stores, scores and alerts. Raises on failure."""
        cycle_start = self.now()

        if self.client is None:
            self.client = self.client_factory()
        if self.since is None:
            self.since = self._initial_since()

        logging.info("Checking for bank notifications received since %s UTC...", self.since)
        messages = self.client.search_messages(since=self.since)
        processed_ids = self.storage.get_processed_ids()

        new_transactions: List[Any] = []
        for message in messages:
            message_id = message.object_id
            if message_id in processed_ids:
                continue

            sender = (self.client.get_header(message, "From") or "").lower()
            if sender not in ALLOWED_SENDERS:
                if message_id not in self.reported_problem_ids:
                    self.reported_problem_ids.add(message_id)
                    logging.warning(
                        "Ignoring email with a bank-like subject from an unknown sender: %s", sender
                    )
                continue

            try:
                transaction = self.parser.parse(
                    message_id=message_id,
                    headers=message,
                    body=self.client.get_body(message),
                    gmail_client=self.client,
                )
            except Exception:
                logging.exception("Could not parse bank email %s", message_id)
                if message_id not in self.reported_problem_ids:
                    self.reported_problem_ids.add(message_id)
                    subject = self.client.get_header(message, "Subject")
                    self.send_message(
                        "⚠️ <b>Fraud bot:</b> a bank email could not be read and was "
                        f"NOT checked:\n{html.escape(subject, quote=False)}"
                    )
                continue

            new_transactions.append(transaction)
            logging.info(
                "New transaction: %s - %s", transaction.amount, transaction.merchant
            )

        inserted = 0
        if new_transactions:
            inserted = self.storage.add_transactions(None, new_transactions, alert_status="pending")

        stats = self._score_pending()
        stats["new"] = inserted

        # Only advance after everything above worked.
        self.since = cycle_start - OVERLAP
        return stats

    def _score_pending(self) -> Dict[str, int]:
        """Scores every pending transaction and delivers the alerts due."""
        stats = {"scored": 0, "alerts": 0, "alerts_failed": 0, "late": 0}

        pending_ids = self.storage.get_pending_ids()
        if not pending_ids:
            return stats

        results = self.scorer(self.storage.load_transactions(), pending_ids)
        max_age = timedelta(hours=ALERT_MAX_AGE_HOURS)
        late: List[Dict[str, Any]] = []

        for result in results:
            stats["scored"] += 1
            message_id = result["message_id"]
            score = result["risk_score"]

            if not result["is_high_risk"]:
                self.storage.set_alert_result(message_id, score, False, "not_needed")
                logging.info(
                    "Transaction at '%s' scored %.2f (low risk).", result["merchant"], score
                )
                continue

            if self._age(result) > max_age:
                self.storage.set_alert_result(message_id, score, True, "skipped_old")
                late.append(result)
                continue

            if self.send_alert(result):
                self.storage.set_alert_result(message_id, score, True, "sent")
                stats["alerts"] += 1
            else:
                # Stays pending: retried on the next cycle.
                self.storage.set_alert_result(message_id, score, True, "pending")
                stats["alerts_failed"] += 1
                logging.error(
                    "Alert for '%s' was not delivered; it will be retried.", result["merchant"]
                )

        if late:
            stats["late"] = len(late)
            self.send_message(self._late_summary(late))

        return stats

    def _age(self, result: Dict[str, Any]) -> timedelta:
        received = pd.to_datetime(result.get("email_date"), errors="coerce", utc=True)
        if pd.isna(received):
            return timedelta(0)
        return self.now() - received.to_pydatetime()

    @staticmethod
    def _late_summary(late: List[Dict[str, Any]]) -> str:
        lines = [
            f"⚠️ <b>Fraud bot:</b> {len(late)} high-risk transaction(s) were found "
            f"late (older than {ALERT_MAX_AGE_HOURS}h), while the bot was not running:",
            "",
        ]
        for result in late[:15]:
            when = result["local_time"].strftime("%d-%m-%Y %H:%M") if result.get("local_time") else "N/A"
            lines.append(
                f"• {html.escape(when)} — {html.escape(str(result.get('currency') or ''))} "
                f"{float(result.get('amount') or 0):,.2f} — "
                f"{html.escape(str(result.get('merchant') or 'Unknown'), quote=False)} "
                f"({float(result.get('risk_score') or 0):.0f}%)"
            )
        if len(late) > 15:
            lines.append(f"…and {len(late) - 15} more.")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Health reporting
    # ------------------------------------------------------------------

    def _on_success(self, stats: Dict[str, int]) -> None:
        if self.consecutive_failures >= FAILURE_ALERT_AFTER and self.first_failure_at:
            minutes = int((self.now() - self.first_failure_at).total_seconds() // 60)
            self.send_message(
                f"✅ <b>Fraud bot recovered</b> after {self.consecutive_failures} failed "
                f"checks (about {minutes} min). Emails from that period have been processed."
            )
        self.consecutive_failures = 0
        self.first_failure_at = None
        self.last_failure_alert_at = None

        if not self.startup_reported:
            self.startup_reported = True
            self.send_message(
                "🟢 <b>Fraud bot started.</b> "
                f"Caught up on {stats.get('new', 0)} new transaction(s), "
                f"{stats.get('alerts', 0)} alert(s) sent."
            )

        self._maybe_heartbeat()

    def _on_failure(self, error: Exception) -> None:
        # A broken client (e.g. expired login) is rebuilt on the next cycle, so
        # a fresh login is picked up without restarting the service.
        self.client = None

        now = self.now()
        self.consecutive_failures += 1
        if self.first_failure_at is None:
            self.first_failure_at = now

        if self.consecutive_failures < FAILURE_ALERT_AFTER:
            return
        reminder_due = (
            self.last_failure_alert_at is None
            or now - self.last_failure_alert_at >= timedelta(hours=FAILURE_REMINDER_HOURS)
        )
        if not reminder_due:
            return

        text = (
            "🔴 <b>Fraud bot is NOT checking your bank emails.</b>\n"
            f"{self.consecutive_failures} checks in a row have failed since "
            f"{self.first_failure_at.strftime('%Y-%m-%d %H:%M')} UTC.\n"
            f"Error: {html.escape(str(error)[:300], quote=False)}"
        )
        if self.send_message(text):
            self.last_failure_alert_at = now

    def _maybe_heartbeat(self) -> None:
        """Sends one 'still alive' message when the local clock passes HEARTBEAT_HOUR."""
        local_now = self.now().astimezone(ZoneInfo(LOCAL_TZ))
        previous_date = self.last_cycle_local_date
        self.last_cycle_local_date = (local_now.date(), local_now.hour)

        if HEARTBEAT_HOUR < 0 or previous_date is None:
            return
        prev_day, prev_hour = previous_date
        crossed = (
            (prev_day == local_now.date() and prev_hour < HEARTBEAT_HOUR <= local_now.hour)
            or (prev_day < local_now.date() and local_now.hour >= HEARTBEAT_HOUR)
        )
        if not crossed:
            return

        total, alerts = self.storage.count_since(self.now() - timedelta(hours=24))
        self.send_message(
            f"🟢 <b>Fraud bot is running.</b> Last 24h: {total} transaction(s), {alerts} alert(s)."
        )

    # ------------------------------------------------------------------
    # Loop
    # ------------------------------------------------------------------

    def run_once(self) -> bool:
        """Runs one cycle with health reporting. Returns True on success."""
        try:
            stats = self.run_check_cycle()
        except Exception as e:
            logging.error("Check cycle failed: %s", e, exc_info=True)
            self._on_failure(e)
            return False
        self._on_success(stats)
        return True

    def start(self) -> None:
        logging.info("Email alert daemon started. Polling every %ss.", self.poll_interval)
        try:
            while self.is_running:
                self.run_once()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            logging.info("Shutting down email alert daemon...")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()],
    )
    EmailAlertService().start()
