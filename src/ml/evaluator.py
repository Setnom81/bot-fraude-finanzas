import pandas as pd
import numpy as np


class FraudEvaluator:
    """
    Hybrid Risk Engine combining unsupervised ML anomaly scores 
    with explicit domain-specific fraud rules.
    """

    def __init__(self, ml_weight: float = 0.3, rules_weight: float = 0.7, risk_threshold: float = 50.0):
        """
        Args:
            ml_weight (float): Weight assigned to Isolation Forest risk score.
            rules_weight (float): Weight assigned to rule-based heuristic score.
            risk_threshold (float): Score cut-off for high risk classification.
        """
        self.ml_weight = ml_weight
        self.rules_weight = rules_weight
        self.risk_threshold = risk_threshold

    def calculate_hybrid_risk(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes rule-based risk indicators and merges them with ML scores.
        """
        df_eval = df.copy()
        rule_scores = pd.Series(0.0, index=df_eval.index)

        # ---------------------------------------------------------
        # Domain Fraud Heuristics (Rule Engine)
        # ---------------------------------------------------------

        # Rule 1: First time transaction at this merchant (+30 pts)
        if "is_new_merchant" in df_eval.columns:
            rule_scores += np.where(df_eval["is_new_merchant"] == 1, 30.0, 0.0)

        # Rule 2: Night transactions (00:00 AM - 05:00 AM) (+20 pts)
        if "is_night_transaction" in df_eval.columns:
            rule_scores += np.where(df_eval["is_night_transaction"] == 1, 20.0, 0.0)

        # Rule 3: Foreign, International or Virtual merchant location (+25 pts)
        if "merchant" in df_eval.columns:
            foreign_keywords = [
                "Reino Unido", "London", "USA", "United States", 
                "Pais no Definido", "Internet", "mulebuy", "415-"
            ]
            pattern = "|".join(foreign_keywords)
            is_foreign = df_eval["merchant"].astype(str).str.contains(pattern, case=False, na=False)
            rule_scores += np.where(is_foreign, 25.0, 0.0)

        # Rule 4: Micro-amount testing transactions ($0.00 to $5.00 / ¢1 to ¢3,000) (+25 pts)
        if "amount" in df_eval.columns:
            # Catches small dollar ($0.01 - $5.00) or low colon charges
            is_micro_test = (df_eval["amount"] >= 0.0) & (df_eval["amount"] <= 5.0)
            rule_scores += np.where(is_micro_test, 25.0, 0.0)

        # Cap rule score at 100 max
        df_eval["rule_risk_score"] = np.clip(rule_scores, 0.0, 100.0)

        # ---------------------------------------------------------
        # Hybrid Score Calculation
        # ---------------------------------------------------------
        if "risk_score" in df_eval.columns:
            df_eval["final_risk_score"] = np.round(
                (df_eval["risk_score"] * self.ml_weight) + 
                (df_eval["rule_risk_score"] * self.rules_weight), 
                2
            )
        else:
            df_eval["final_risk_score"] = df_eval["rule_risk_score"]

        # Flag high risk using threshold (>= 50.0)
        df_eval["is_high_risk"] = df_eval["final_risk_score"] >= self.risk_threshold

        return df_eval