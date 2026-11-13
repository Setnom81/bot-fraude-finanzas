"""Scoring tests. Run from the project root: .venv/bin/python -m unittest discover -s tests -v"""

import logging
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.alerts.telegram import format_alert
from src.ml.data_preprocessing import DataPreprocessor, is_foreign_location, split_merchant
from src.ml.evaluator import FraudEvaluator
from src.ml.inference import score_transactions
from src.ml.model import FraudDetector

logging.disable(logging.CRITICAL)

LOCAL_SHOP = "SUPER LOCAL Ciudad y país: SAN JOSE, Costa Rica"


def make_tx(i, merchant=LOCAL_SHOP, amount=5000.0, currency="CRC", when=None, subject_time=None):
    """One stored-row-like dict. `when` is the email arrival time in UTC."""
    when = when or datetime(2026, 6, 1, 18, 0) + timedelta(hours=7 * i)
    subject = "Notificación de transacción X"
    if subject_time:
        subject += f" {subject_time}"
    return {
        "message_id": f"id-{i}",
        "merchant": merchant,
        "amount": f"{currency} {amount:,.2f}",
        "amount_value": amount,
        "currency": currency,
        "card_last4": "1234",
        "email_subject": subject,
        "email_date": when.isoformat(),
    }


def make_history(n=80):
    """Routine local purchases between CRC 3,000 and 7,000 at five shops."""
    return [
        make_tx(
            i,
            merchant=f"SHOP {i % 5} Ciudad y país: SAN JOSE, Costa Rica",
            amount=3000.0 + (i * 37 % 40) * 100,
        )
        for i in range(n)
    ]


class MerchantTests(unittest.TestCase):
    def test_split_merchant(self):
        self.assertEqual(
            split_merchant("Abastecedor 3A Ciudad y país: SAN JOSE, Costa Rica"),
            ("ABASTECEDOR 3A", "SAN JOSE, Costa Rica"),
        )
        self.assertEqual(split_merchant("PLAIN NAME"), ("PLAIN NAME", ""))
        self.assertEqual(split_merchant(None), ("", ""))

    def test_foreign_location(self):
        self.assertFalse(is_foreign_location("HEREDIA, Costa Rica"))
        self.assertTrue(is_foreign_location("London, Reino Unido"))
        self.assertTrue(is_foreign_location("650-2530000, Pais no Definido"))
        self.assertTrue(is_foreign_location("g.co/helppay, "))
        self.assertFalse(is_foreign_location(""))


class PreprocessingTests(unittest.TestCase):
    def setUp(self):
        self.pre = DataPreprocessor()

    def test_new_merchant_is_flagged_even_when_rows_are_newest_first(self):
        rows = make_history(40) + [make_tx(40, merchant="NEVER SEEN Ciudad y país: X, Costa Rica")]
        rows.append(make_tx(41, merchant="SHOP 1 Ciudad y país: SAN JOSE, Costa Rica"))
        out = self.pre.fit_transform(pd.DataFrame(list(reversed(rows)))).set_index("message_id")
        self.assertEqual(out.loc["id-40", "is_new_merchant"], 1)
        self.assertEqual(out.loc["id-41", "is_new_merchant"], 0)
        self.assertEqual(out.loc["id-41", "merchant_tx_count_so_far"], 8)

    def test_features_only_use_earlier_transactions(self):
        history = make_history(50)
        before = self.pre.fit_transform(pd.DataFrame(history)).set_index("message_id")
        later = history + [make_tx(50, amount=900000.0)]
        after = self.pre.fit_transform(pd.DataFrame(later)).set_index("message_id")
        cols = self.pre.get_feature_columns()
        pd.testing.assert_frame_equal(before[cols], after.loc[before.index, cols])

    def test_usd_is_converted_before_comparing_amounts(self):
        rows = make_history(60) + [make_tx(60, amount=400.0, currency="USD")]
        out = self.pre.fit_transform(pd.DataFrame(rows)).set_index("message_id")
        self.assertEqual(out.loc["id-60", "amount_crc"], 200000.0)
        self.assertGreater(out.loc["id-60", "amount_zscore"], 3.0)

    def test_hours_are_local_time(self):
        rows = [
            # 02:02 UTC is 20:02 the previous day in Costa Rica: not night.
            make_tx(0, when=datetime(2026, 9, 4, 2, 2)),
            # The subject carries the bank's local time and wins: 03:10 is night.
            make_tx(1, when=datetime(2026, 9, 4, 9, 11), subject_time="04-09-2026 - 03:10"),
        ]
        out = self.pre.fit_transform(pd.DataFrame(rows)).set_index("message_id")
        self.assertEqual(out.loc["id-0", "hour"], 20)
        self.assertEqual(out.loc["id-0", "is_night_transaction"], 0)
        self.assertEqual(out.loc["id-1", "hour"], 3)
        self.assertEqual(out.loc["id-1", "is_night_transaction"], 1)


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = DataPreprocessor()
        cls.history = make_history(200)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.model_path = Path(cls.tmp.name) / "model.joblib"
        features = cls.pre.fit_transform(pd.DataFrame(cls.history))
        detector = FraudDetector()
        detector.train(features[cls.pre.get_feature_columns()])
        detector.save_model(cls.model_path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_score_does_not_depend_on_the_batch(self):
        detector = FraudDetector()
        detector.load_model(self.model_path)
        rows = self.history + [
            make_tx(200, merchant="ODD Ciudad y país: London, Reino Unido", amount=450000.0),
            make_tx(201, merchant="SHOP 1 Ciudad y país: SAN JOSE, Costa Rica", amount=4500.0),
        ]
        X = self.pre.fit_transform(pd.DataFrame(rows))[self.pre.get_feature_columns()]
        batch = detector.predict(X.tail(2))["risk_score"].tolist()
        alone = [detector.predict(X.iloc[[-2]])["risk_score"].iloc[0],
                 detector.predict(X.iloc[[-1]])["risk_score"].iloc[0]]
        self.assertEqual(batch, alone)
        self.assertGreater(alone[0], 90.0)   # clear outlier
        self.assertLess(alone[1], alone[0])  # routine purchase scores lower

    def test_large_purchase_at_new_foreign_merchant_is_high_risk(self):
        rows = self.history + [
            make_tx(200, merchant="UNKNOWN STORE Ciudad y país: London, Reino Unido", amount=450000.0),
            make_tx(201, merchant="SHOP 2 Ciudad y país: SAN JOSE, Costa Rica", amount=4200.0),
        ]
        results = {r["message_id"]: r for r in score_transactions(rows, {"id-200", "id-201"}, self.model_path)}
        self.assertTrue(results["id-200"]["is_high_risk"])
        self.assertIn("large amount at new merchant", results["id-200"]["reasons"])
        self.assertEqual(results["id-200"]["merchant"], "UNKNOWN STORE")
        self.assertFalse(results["id-201"]["is_high_risk"])

    def test_rows_that_already_carry_stored_results_can_be_scored(self):
        rows = [dict(r, risk_score=12.5, is_high_risk=0, alert_status="not_needed", alerted_at=None)
                for r in self.history]
        rows.append(dict(make_tx(200), risk_score=None, is_high_risk=None, alert_status="pending", alerted_at=None))
        results = score_transactions(rows, {"id-200"}, self.model_path)
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0]["risk_score"], float)

    def test_missing_model_is_an_error_not_a_silent_skip(self):
        with self.assertRaises(FileNotFoundError):
            score_transactions(self.history, {"id-1"}, Path(self.tmp.name) / "nope.joblib")


class RuleTests(unittest.TestCase):
    def evaluate(self, **features):
        row = {
            "merchant": LOCAL_SHOP, "is_new_merchant": 0, "is_night_transaction": 0,
            "is_foreign": 0, "amount_usd_equiv": 20.0, "amount_zscore": 0.0, "risk_score": 0.0,
        }
        row.update(features)
        return FraudEvaluator().calculate_hybrid_risk(pd.DataFrame([row])).iloc[0]

    def test_small_purchase_at_known_local_shop_scores_zero(self):
        self.assertEqual(self.evaluate(amount_usd_equiv=2.0)["rule_risk_score"], 0.0)

    def test_micro_charge_at_new_foreign_merchant(self):
        out = self.evaluate(amount_usd_equiv=1.0, is_new_merchant=1, is_foreign=1)
        self.assertEqual(out["rule_risk_score"], 70.0)  # 20 + 25 + 25

    def test_new_merchant_with_large_amount_alerts_without_ml(self):
        out = self.evaluate(is_new_merchant=1, amount_zscore=4.0)
        self.assertEqual(out["rule_risk_score"], 100.0)
        self.assertTrue(out["is_high_risk"])


class TelegramFormatTests(unittest.TestCase):
    def test_merchant_text_is_escaped(self):
        text = format_alert({
            "merchant": "A&B <SHOP>", "location": "X, Costa Rica", "amount": 1500.5,
            "currency": "CRC", "risk_score": 180.0, "reasons": ["new merchant"],
            "local_time": datetime(2026, 9, 4, 20, 2),
        })
        self.assertIn("A&amp;B &lt;SHOP&gt;", text)
        self.assertNotIn("<SHOP>", text)
        self.assertIn("100.00%", text)
        self.assertIn("04-09-2026 20:02", text)


if __name__ == "__main__":
    unittest.main()
