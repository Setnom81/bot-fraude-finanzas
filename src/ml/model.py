import logging
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


# Anomaly percentile (vs. training data) at which the ML risk starts rising
# from 0. With 0.8, the most unusual 20% of transactions get a non-zero ML
# risk, the top 10% get 50 or more, and the top 3% get 85 or more.
RISK_FLOOR_PERCENTILE = 0.8


class FraudDetector:
    """Isolation Forest wrapper that turns anomaly scores into a 0-100 risk.

    The risk of a transaction is measured against the scores seen in training,
    so it does not depend on which other transactions are scored with it.
    """

    def __init__(self, contamination: float = 0.03, random_state: int = 42):
        self.contamination = contamination
        self.random_state = random_state
        self.model = IsolationForest(
            contamination=self.contamination,
            random_state=self.random_state,
            n_estimators=100,
            n_jobs=-1,
        )
        self.train_scores: np.ndarray | None = None
        self.feature_columns: list[str] | None = None
        self.trained_at: str | None = None
        self.is_fitted = False

    def train(self, X: pd.DataFrame) -> None:
        """Fits the model and keeps the training score distribution."""
        if X.empty:
            raise ValueError("Training matrix X is empty.")

        self.model.fit(X)
        self.train_scores = np.sort(self.model.score_samples(X))
        self.feature_columns = list(X.columns)
        self.trained_at = datetime.now(timezone.utc).isoformat()
        self.is_fitted = True

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        """Returns 'is_anomaly' (-1 outlier, 1 normal) and 'risk_score' (0-100).

        risk_score is 0 up to the RISK_FLOOR_PERCENTILE of training anomaly
        scores and reaches 100 for a transaction more unusual than
        everything seen in training.
        """
        if not self.is_fitted:
            raise RuntimeError("Model must be trained or loaded before predict().")

        if X.empty:
            return pd.DataFrame(columns=["is_anomaly", "risk_score"])

        raw_preds = self.model.predict(X)

        if self.train_scores is None or len(self.train_scores) == 0:
            # Model file saved by an older version: no reference distribution.
            logging.warning(
                "Model has no training score reference; retrain with "
                "'python -m src.ml.train' for graded risk scores."
            )
            risk_scores = np.where(raw_preds == -1, 100.0, 0.0)
        else:
            # Lower score_samples = more anomalous.
            scores = self.model.score_samples(X)
            more_anomalous = np.searchsorted(self.train_scores, scores, side="left")
            percentile = 1.0 - more_anomalous / len(self.train_scores)
            risk_scores = 100.0 * np.clip(
                (percentile - RISK_FLOOR_PERCENTILE) / (1.0 - RISK_FLOOR_PERCENTILE),
                0.0,
                1.0,
            )

        return pd.DataFrame(
            {"is_anomaly": raw_preds, "risk_score": np.round(risk_scores, 2)},
            index=X.index,
        )

    def save_model(self, filepath: str | Path) -> None:
        """Writes the model and its score reference to disk."""
        if not self.is_fitted:
            raise RuntimeError("Cannot save an untrained model instance.")
        joblib.dump(
            {
                "model": self.model,
                "train_scores": self.train_scores,
                "feature_columns": self.feature_columns,
                "trained_at": self.trained_at,
            },
            filepath,
        )

    def load_model(self, filepath: str | Path) -> None:
        """Loads a model file (current format, or a bare model from older versions)."""
        artifact = joblib.load(filepath)
        if isinstance(artifact, dict):
            self.model = artifact["model"]
            self.train_scores = artifact.get("train_scores")
            self.feature_columns = artifact.get("feature_columns")
            self.trained_at = artifact.get("trained_at")
        else:
            self.model = artifact
            self.train_scores = None
            self.feature_columns = None
            self.trained_at = None
        self.is_fitted = True
