from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from src.config import MODEL_PATH
from src.ml.data_preprocessing import DataPreprocessor
from src.ml.evaluator import FraudEvaluator
from src.ml.model import FraudDetector

# Results stored by earlier runs; they are recomputed here and must not be
# mistaken for inputs.
STORED_RESULT_COLUMNS = ["risk_score", "is_high_risk", "alert_status", "alerted_at"]


def build_evaluated_frame(
    transactions: List[Dict[str, Any]], model_path: Optional[Path] = None
) -> pd.DataFrame:
    """Computes features, ML score and rule score for every given transaction.

    Features of each row only use rows that arrived before it, so passing the
    full history plus the new rows scores the new rows against real history.

    Raises:
        FileNotFoundError: the trained model file does not exist.
    """
    model_path = Path(model_path or MODEL_PATH)
    if not model_path.exists():
        raise FileNotFoundError(
            f"Trained model not found at {model_path}. Run 'python -m src.ml.train' first."
        )

    df = pd.DataFrame(transactions)
    if df.empty:
        return df
    df = df.drop(columns=STORED_RESULT_COLUMNS, errors="ignore")

    preprocessor = DataPreprocessor()
    df_processed = preprocessor.fit_transform(df).reset_index(drop=True)

    detector = FraudDetector()
    detector.load_model(model_path)
    feature_cols = detector.feature_columns or preprocessor.get_feature_columns()
    ml_results = detector.predict(df_processed[feature_cols])

    df_eval_input = pd.concat([df_processed, ml_results], axis=1)
    return FraudEvaluator(
        ml_weight=0.5, rules_weight=0.5, risk_threshold=50.0
    ).calculate_hybrid_risk(df_eval_input)


def score_transactions(
    transactions: List[Dict[str, Any]],
    target_ids: Iterable[str],
    model_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Scores the transactions whose message_id is in target_ids.

    Args:
        transactions: Full history including the rows to score, as dicts with
            at least message_id, merchant, amount/amount_value, currency,
            email_date and email_subject.
        target_ids: message_ids to return results for.

    Returns:
        One result dict per target transaction.
    """
    target_ids = set(target_ids)
    if not target_ids or not transactions:
        return []

    evaluated = build_evaluated_frame(transactions, model_path)
    targets = evaluated[evaluated["message_id"].isin(target_ids)]

    results: List[Dict[str, Any]] = []
    for _, row in targets.iterrows():
        local_time = row.get("local_time")
        results.append(
            {
                "message_id": row["message_id"],
                "merchant": row.get("merchant_name") or "Unknown",
                "location": row.get("merchant_location") or "",
                "amount": float(row.get("amount_num", 0.0)),
                "currency": row.get("currency") or "",
                "card_last4": row.get("card_last4") or "",
                "local_time": None if pd.isna(local_time) else local_time.to_pydatetime(),
                "email_date": row.get("email_date"),
                "ml_risk_score": float(row.get("risk_score", 0.0)),
                "rule_risk_score": float(row.get("rule_risk_score", 0.0)),
                "risk_score": float(row.get("final_risk_score", 0.0)),
                "is_high_risk": bool(row.get("is_high_risk", False)),
                "reasons": list(row.get("reasons") or []),
            }
        )
    return results
