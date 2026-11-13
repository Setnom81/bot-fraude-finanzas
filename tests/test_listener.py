"""Listener tests with in-memory fakes (no MySQL, Outlook or Telegram needed)."""

import logging
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.ingestion.parsers.bac_parser import BacParser
from src.services.outlook_listener import OVERLAP, EmailAlertService

logging.disable(logging.CRITICAL)

BANK = "notificacion@notificacionesbaccr.com"
T0 = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)


def email(message_id, merchant="SUPER LOCAL", received=T0, sender=BANK, amount="CRC 5,000.00"):
    body = (
        f"Comercio: {merchant} Ciudad y país: SAN JOSE, Costa Rica "
        f"Fecha: Sep 10, 2026 Monto: {amount} Tarjeta ****1234 Autorización: 123456"
    )
    return SimpleNamespace(
        object_id=message_id,
        subject=f"Notificación de transacción {merchant} 10-09-2026 - 09:00",
        received=received,
        sender=SimpleNamespace(address=sender),
        to=[SimpleNamespace(address="me@example.com")],
        body=body,
    )


class FakeClient:
    def __init__(self, inbox):
        self.inbox = inbox
        self.fail = None
        self.since_seen = []

    def search_messages(self, query=None, since=None):
        if self.fail:
            raise self.fail
        self.since_seen.append(since)
        return [m for m in self.inbox if m.received >= since]

    def get_header(self, message, name):
        name = name.lower()
        if name == "subject":
            return message.subject
        if name == "from":
            return message.sender.address
        if name == "to":
            return ", ".join(r.address for r in message.to)
        return message.received.isoformat()

    def get_body(self, message):
        return message.body


class FakeStorage:
    def __init__(self):
        self.rows = {}

    def get_latest_email_date(self):
        dates = [datetime.fromisoformat(r["email_date"]).replace(tzinfo=None) for r in self.rows.values()]
        return max(dates) if dates else None

    def get_processed_ids(self):
        return set(self.rows)

    def get_pending_ids(self):
        return {k for k, r in self.rows.items() if r["alert_status"] == "pending"}

    def load_transactions(self):
        return list(self.rows.values())

    def add_transactions(self, data, transactions, alert_status="pending"):
        inserted = 0
        for t in transactions:
            item = t.to_dict()
            if item["message_id"] not in self.rows:
                item["alert_status"] = alert_status
                self.rows[item["message_id"]] = item
                inserted += 1
        return inserted

    def set_alert_result(self, message_id, risk_score, is_high_risk, alert_status):
        self.rows[message_id].update(
            risk_score=risk_score, is_high_risk=is_high_risk, alert_status=alert_status
        )

    def count_since(self, since_utc):
        return len(self.rows), sum(r["alert_status"] == "sent" for r in self.rows.values())


def fake_scorer(transactions, target_ids):
    """High risk when the merchant contains EVIL."""
    return [
        {
            "message_id": t["message_id"], "merchant": t["merchant"], "location": "",
            "amount": 1.0, "currency": "CRC", "card_last4": "", "local_time": None,
            "email_date": t["email_date"], "risk_score": 90.0 if "EVIL" in t["merchant"] else 5.0,
            "is_high_risk": "EVIL" in t["merchant"], "reasons": [],
        }
        for t in transactions if t["message_id"] in target_ids
    ]


class ListenerTests(unittest.TestCase):
    def setUp(self):
        self.clock = T0 + timedelta(minutes=1)
        self.inbox = []
        self.client = FakeClient(self.inbox)
        self.storage = FakeStorage()
        self.alerts, self.messages = [], []
        self.telegram_up = True
        self.service = EmailAlertService(
            storage=self.storage,
            client_factory=lambda: self.client,
            parser=BacParser(),
            scorer=fake_scorer,
            send_alert=lambda r: self.telegram_up and (self.alerts.append(r["message_id"]) or True),
            send_message=lambda text: self.telegram_up and (self.messages.append(text) or True),
            now=lambda: self.clock,
        )

    def tick(self, minutes=2):
        self.clock += timedelta(minutes=minutes)
        return self.service.run_once()

    def test_low_and_high_risk_flow(self):
        self.inbox += [email("a"), email("b", merchant="EVIL CORP")]
        self.assertTrue(self.tick())
        self.assertEqual(self.storage.rows["a"]["alert_status"], "not_needed")
        self.assertEqual(self.storage.rows["b"]["alert_status"], "sent")
        self.assertEqual(self.alerts, ["b"])
        # A second cycle does not alert again.
        self.tick()
        self.assertEqual(self.alerts, ["b"])
        self.assertEqual(self.storage.rows["a"]["email_to"], "me@example.com")

    def test_alert_is_retried_until_delivered(self):
        self.inbox.append(email("b", merchant="EVIL CORP"))
        self.telegram_up = False
        self.tick()
        self.assertEqual(self.storage.rows["b"]["alert_status"], "pending")
        self.assertEqual(self.alerts, [])
        self.telegram_up = True
        self.tick()
        self.assertEqual(self.storage.rows["b"]["alert_status"], "sent")
        self.assertEqual(self.alerts, ["b"])

    def test_email_that_arrived_during_an_outage_is_still_alerted(self):
        self.tick()  # healthy cycle, establishes the reading position
        self.client.fail = RuntimeError("No auth token found")
        for _ in range(30):  # one hour of failures
            self.assertFalse(self.tick())
        self.inbox.append(email("late", merchant="EVIL CORP", received=T0 + timedelta(minutes=20)))
        self.client.fail = None
        self.assertTrue(self.tick())
        self.assertEqual(self.alerts, ["late"])

    def test_failure_alert_and_recovery_message(self):
        self.tick()
        self.messages.clear()
        self.client.fail = RuntimeError("invalid_client <boom>")
        self.tick(); self.tick()
        self.assertEqual(self.messages, [])          # not yet: 2 failures
        self.tick()
        self.assertEqual(len(self.messages), 1)       # 3rd failure
        self.assertIn("NOT checking", self.messages[0])
        self.assertIn("&lt;boom&gt;", self.messages[0])
        for _ in range(10):
            self.tick()
        self.assertEqual(len(self.messages), 1)       # no spam within 6h
        self.client.fail = None
        self.tick()
        self.assertIn("recovered", self.messages[-1])

    def test_reading_position_only_advances_on_success(self):
        self.tick()
        position = self.service.since
        self.client.fail = RuntimeError("down")
        self.tick()
        self.assertEqual(self.service.since, position)
        self.client.fail = None
        self.tick()
        self.assertEqual(self.service.since, self.clock - OVERLAP)

    def test_restart_resumes_from_newest_stored_email(self):
        self.inbox.append(email("a", received=T0 - timedelta(days=20)))
        self.storage.add_transactions(None, [BacParser().parse("a", self.inbox[0], self.inbox[0].body, self.client)], "not_needed")
        self.inbox.append(email("gap", merchant="EVIL CORP", received=T0 - timedelta(days=10)))
        self.tick()
        self.assertIn("gap", self.storage.rows)
        # Ten days old: no individual alert, one late summary instead.
        self.assertEqual(self.storage.rows["gap"]["alert_status"], "skipped_old")
        self.assertEqual(self.alerts, [])
        self.assertTrue(any("found late" in m or "were found" in m for m in self.messages))

    def test_unknown_sender_is_ignored(self):
        self.inbox.append(email("spoof", merchant="EVIL CORP", sender="attacker@example.com"))
        self.tick()
        self.assertEqual(self.storage.rows, {})
        self.assertEqual(self.alerts, [])

    def test_startup_message_is_sent_once(self):
        self.tick(); self.tick(); self.tick()
        self.assertEqual(sum("started" in m for m in self.messages), 1)

    def test_daily_heartbeat_when_local_clock_passes_8am(self):
        # 13:30 UTC = 07:30 in Costa Rica.
        self.clock = datetime(2026, 9, 11, 13, 30, tzinfo=timezone.utc)
        self.tick(0)
        self.messages.clear()
        self.tick(20)   # 07:50
        self.assertEqual(self.messages, [])
        self.tick(20)   # 08:10
        self.assertEqual(sum("is running" in m for m in self.messages), 1)
        self.tick(20)
        self.assertEqual(sum("is running" in m for m in self.messages), 1)


if __name__ == "__main__":
    unittest.main()
