import logging
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

from src.alerts.telegram import send_telegram_alert
from src.database.storage import TransactionStorage
from src.ml.data_preprocessing import DataPreprocessor
from src.ml.evaluator import FraudEvaluator
from src.ml.model import FraudDetector


def process_and_alert_new_transactions(new_transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Evaluates incoming transaction payloads against a hybrid risk architecture.

    Integrates Isolation Forest unsupervised anomaly scores with a domain heuristic
    rule engine, triggering instant alerts for high-risk transactions.

    Args:
        new_transactions (List[Dict[str, Any]]): List of newly parsed transaction dictionaries.

    Returns:
        List[Dict[str, Any]]: List of high-risk transaction records flagged by the evaluator.
    """
    if not new_transactions:
        logging.info("Empty transaction payload received. Aborting inference execution.")
        return []

    # 1. Model Artifact Verification
    model_path = Path("models/fraud_model.joblib")
    if not model_path.exists():
        logging.warning("Trained model binary not found at %s. Execute training pipeline first.", model_path)
        return []

    # 2. Historical Context Retrieval & State Isolation
    storage = TransactionStorage()
    historical_raw = storage.load().get("transactions", [])
    
    df_history = pd.DataFrame(historical_raw)
    df_new = pd.DataFrame(new_transactions)

    # Preventing Historical Context Pollution: If incoming records were pre-persisted 
    # to storage prior to evaluation, slice out the tail records to ensure 
    # sequential feature engineering (e.g., 'is_new_merchant') remains accurate.
    if not df_history.empty and "merchant" in df_history.columns:
        df_history = df_history[~df_history.index.isin(df_history.tail(len(new_transactions)).index)]

    # Concatenate historical baseline with newly arrived slice for sequential feature engineering
    df_combined = pd.concat([df_history, df_new], ignore_index=True)

    # 3. Feature Preprocessing & Transformation Pipeline
    preprocessor = DataPreprocessor()
    df_processed = preprocessor.fit_transform(df_combined)
    feature_cols = preprocessor.get_feature_columns()

    # Extract new transaction feature vector and explicitly reset index to prevent structural misalignment
    df_new_features = df_processed.iloc[-len(new_transactions):].reset_index(drop=True)

    # 4. Machine Learning Model Inference
    detector = FraudDetector()
    detector.load_model(model_path)
    
    # Execute batch anomaly scoring and guarantee zero-indexed DataFrame alignment
    ml_results = detector.predict(df_new_features[feature_cols]).reset_index(drop=True)

    # 5. Matrix Concatenation & Index Alignment Fix
    # Perform column-wise concatenation on strictly aligned zero-based indices to eliminate NaNs
    df_eval_input = pd.concat([df_new_features, ml_results], axis=1)

    # 6. Hybrid Risk Engine Evaluation
    evaluator = FraudEvaluator(ml_weight=0.5, rules_weight=0.5, risk_threshold=50.0)
    df_evaluated = evaluator.calculate_hybrid_risk(df_eval_input)

    # 7. Decision Routing & Alert Dispatch Loop
    high_risk_list: List[Dict[str, Any]] = []

    for idx, row in df_evaluated.iterrows():
        tx_dict = row.to_dict()
        
        # Extract evaluated hybrid risk score, safely defaulting NaN values to zero float
        raw_score = row.get("final_risk_score", row.get("hybrid_risk_score", 0.0))
        risk_score = 0.0 if pd.isna(raw_score) else float(raw_score)
        
        merchant = row.get("merchant", "Unknown")

        # Evaluate classification decision against policy threshold
        if row.get("is_high_risk", False):
            tx_dict["risk_score"] = risk_score
            send_telegram_alert(transaction=tx_dict, risk_score=risk_score)
            high_risk_list.append(tx_dict)
        else:
            logging.info(
                "Transaction at '%s' processed with a low risk score of %.2f", 
                merchant, risk_score
            )

    return high_risk_list