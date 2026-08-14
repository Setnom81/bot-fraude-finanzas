from pathlib import Path
import pandas as pd
import logging
from src.database.storage import TransactionStorage
from src.ml.data_preprocessing import DataPreprocessor
from src.ml.model import FraudDetector
from src.ml.evaluator import FraudEvaluator
from src.alerts.telegram import send_telegram_alert


def process_and_alert_new_transactions(new_transactions: list[dict]) -> list[dict]:
    """
    Evaluates newly fetched transactions against the ML model + Rule Engine
    and triggers instant notifications via Telegram if high risk.

    Args:
        new_transactions (list[dict]): List of newly parsed transaction dictionaries.

    Returns:
        list[dict]: List of high-risk transactions triggered.
    """
    if not new_transactions:
        return []

    model_path = Path("models/fraud_model.joblib")
    if not model_path.exists():
        print("Model artifact not found. Please run 'python -m src.ml.train' first.")
        return []

    # 1. Combine historical data with new ones to accurately calculate 'is_new_merchant'
    storage = TransactionStorage()
    historical_raw = storage.load().get("transactions", [])
    
    df_history = pd.DataFrame(historical_raw)
    df_new = pd.DataFrame(new_transactions)

    # Combine history + new to compute sequential features
    df_combined = pd.concat([df_history, df_new], ignore_index=True)

    # 2. Preprocess combined dataframe
    preprocessor = DataPreprocessor()
    df_processed = preprocessor.fit_transform(df_combined)
    feature_cols = preprocessor.get_feature_columns()

    # Get index slice corresponding to newly arrived transactions only
    new_indices = df_processed.index[-len(new_transactions):]
    df_new_features = df_processed.loc[new_indices]

    # 3. Load trained model & predict
    detector = FraudDetector()
    detector.load_model(model_path)
    ml_results = detector.predict(df_new_features[feature_cols])

    # 4. Evaluate hybrid risk score on new transactions
    df_eval_input = df_new_features.join(ml_results)
    evaluator = FraudEvaluator(ml_weight=0.3, rules_weight=0.7, risk_threshold=50.0)
    df_evaluated = evaluator.calculate_hybrid_risk(df_eval_input)

    # 5. Filter high-risk transactions and trigger Telegram alerts
    high_risk_list = []

    for idx, row in df_evaluated.iterrows():
        tx_dict = row.to_dict()
        risk_score = row.get("hybrid_risk_score", 0.0)
        merchant = row.get("merchant", "Unknown")

        # Sends Telegram alert if necessary or just logs score.
        if row.get("is_high_risk", False):
            send_telegram_alert(transaction=tx_dict, risk_score=risk_score)
            high_risk_list.append(tx_dict)
        else:
            score_fmt = f"{risk_score:.2f}" if isinstance(risk_score, (int, float)) else risk_score
            logging.info(f"Transaction at '{merchant}' processed with a low risk score of {score_fmt}")

    return high_risk_list