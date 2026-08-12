from pathlib import Path
import pandas as pd
from src.database.storage import TransactionStorage
from src.ml.data_preprocessing import DataPreprocessor
from src.ml.model import FraudDetector


def train_and_save_model():
    """
    Loads full history from MySQL, fits IsolationForest on processed features,
    and serializes model to models/fraud_model.joblib.
    """
    model_dir = Path("models")
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "fraud_model.joblib"

    print("Loading historical data for training...")
    storage = TransactionStorage()
    raw_data = storage.load().get("transactions", [])

    if not raw_data:
        print("No historical transactions found for training.")
        return

    df_raw = pd.DataFrame(raw_data)
    preprocessor = DataPreprocessor()
    df_processed = preprocessor.fit_transform(df_raw)
    feature_cols = preprocessor.get_feature_columns()

    print("Training Isolation Forest model...")
    detector = FraudDetector(contamination=0.03, random_state=42)
    detector.train(df_processed[feature_cols])

    detector.save_model(model_path)
    print(f"Model successfully saved to {model_path}")


if __name__ == "__main__":
    train_and_save_model()