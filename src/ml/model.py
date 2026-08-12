import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
import joblib
from pathlib import Path


class FraudDetector:
    """
    Unsupervised Anomaly Detection wrapper using Isolation Forest.
    Calculates raw anomaly predictions and normalizes output into a 0-100 Risk Score.
    """

    def __init__(self, contamination: float = 0.03, random_state: int = 42):
        """
        Args:
            contamination (float): Expected proportion of outliers/anomalies in dataset (e.g. 0.03 = 3%).
            random_state (int): Seed for reproducibility.
        """
        self.contamination = contamination
        self.random_state = random_state
        self.model = IsolationForest(
            contamination=self.contamination,
            random_state=self.random_state,
            n_estimators=100,
            n_jobs=-1
        )
        self.is_fitted = False

    def train(self, X: pd.DataFrame) -> None:
        """
        Fits the Isolation Forest model on numerical feature matrix.
        """
        if X.empty:
            raise ValueError("Training matrix X is empty.")

        self.model.fit(X)
        self.is_fitted = True

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Generates predictions and risk scores for input features.

        Returns:
            pd.DataFrame: Contains 'is_anomaly' (-1 for outlier, 1 for normal)
                          and 'risk_score' (float bounded between 0 and 100).
        """
        if not self.is_fitted:
            raise RuntimeError("Model must be trained via fit() before calling predict().")

        if X.empty:
            return pd.DataFrame(columns=["is_anomaly", "risk_score"])

        # 1. Raw Isolation Forest predictions: -1 = Anomaly, 1 = Normal
        raw_preds = self.model.predict(X)

        # 2. Decision function scores: Lower/negative values indicate higher anomaly degree
        scores = self.model.decision_function(X)

        # 3. Transform decision score into normalized Risk Score (0 to 100)
        # Offset decision scores relative to zero baseline
        min_score, max_score = scores.min(), scores.max()
        
        if max_score == min_score:
            risk_scores = np.full_like(scores, 50.0)
        else:
            # Invert scale so lower decision scores map to higher risk values
            risk_scores = 100 * (1.0 - (scores - min_score) / (max_score - min_score))

        results = pd.DataFrame({
            "is_anomaly": raw_preds,
            "risk_score": np.round(risk_scores, 2)
        }, index=X.index)

        return results

    def save_model(self, filepath: str | Path) -> None:
        """
        Serializes trained model artifact to disk.
        """
        if not self.is_fitted:
            raise RuntimeError("Cannot save an untrained model instance.")
        joblib.dump(self.model, filepath)

    def load_model(self, filepath: str | Path) -> None:
        """
        Deserializes trained model artifact from disk.
        """
        self.model = joblib.load(filepath)
        self.is_fitted = True