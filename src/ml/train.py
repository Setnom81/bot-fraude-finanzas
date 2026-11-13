import pandas as pd

from src.config import MODEL_PATH
from src.database.storage import TransactionStorage
from src.ml.data_preprocessing import DataPreprocessor
from src.ml.model import FraudDetector


def train_and_save_model(model_path=MODEL_PATH):
    """Fits the Isolation Forest on the full MySQL history and saves it."""
    model_path.parent.mkdir(parents=True, exist_ok=True)

    print("Loading historical data for training...")
    raw_data = TransactionStorage().load_transactions()

    if not raw_data:
        print("No historical transactions found for training.")
        return

    preprocessor = DataPreprocessor()
    df_processed = preprocessor.fit_transform(pd.DataFrame(raw_data))
    feature_cols = preprocessor.get_feature_columns()

    print(f"Training Isolation Forest model on {len(df_processed)} transactions...")
    detector = FraudDetector(contamination=0.03, random_state=42)
    detector.train(df_processed[feature_cols])

    detector.save_model(model_path)
    print(f"Model successfully saved to {model_path}")


if __name__ == "__main__":
    train_and_save_model()
