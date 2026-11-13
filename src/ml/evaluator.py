import numpy as np
import pandas as pd

# Extra hints of a foreign or online-only merchant, matched on the raw text.
FOREIGN_KEYWORDS = [
    "Reino Unido", "London", "USA", "United States",
    "Pais no Definido", "Internet", "mulebuy", "415-",
]

MICRO_AMOUNT_USD = 5.0


class FraudEvaluator:
    """Hybrid risk engine: ML anomaly score combined with explicit rules.

    final_risk_score = ml_weight * ML score + rules_weight * rule score,
    and a transaction is high risk when that reaches risk_threshold.
    """

    def __init__(self, ml_weight: float = 0.5, rules_weight: float = 0.5, risk_threshold: float = 50.0):
        self.ml_weight = ml_weight
        self.rules_weight = rules_weight
        self.risk_threshold = risk_threshold

    def calculate_hybrid_risk(self, df: pd.DataFrame) -> pd.DataFrame:
        """Adds rule_risk_score, final_risk_score, is_high_risk and reasons."""
        df_eval = df.copy()
        index = df_eval.index
        rule_scores = pd.Series(0.0, index=index)
        reasons = pd.Series([[] for _ in range(len(df_eval))], index=index)

        def flag(column: str) -> pd.Series:
            if column in df_eval.columns:
                return df_eval[column].fillna(0).astype(int) == 1
            return pd.Series(False, index=index)

        def number(column: str) -> pd.Series:
            if column in df_eval.columns:
                return pd.to_numeric(df_eval[column], errors="coerce").fillna(0.0)
            return pd.Series(0.0, index=index)

        def apply(mask: pd.Series, points: float, label: str) -> None:
            nonlocal rule_scores
            rule_scores = rule_scores + np.where(mask, points, 0.0)
            for i in index[mask.to_numpy()]:
                reasons.at[i].append(label)

        is_new = flag("is_new_merchant")
        zscore = number("amount_zscore")

        # Rule 1: first purchase at this merchant (+20)
        apply(is_new, 20.0, "new merchant")

        # Rule 2: between 00:00 and 05:59 local time (+10)
        apply(flag("is_night_transaction"), 10.0, "night-time")

        # Rule 3: foreign or online-only merchant (+25)
        is_foreign = flag("is_foreign")
        if "merchant" in df_eval.columns:
            pattern = "|".join(FOREIGN_KEYWORDS)
            is_foreign = is_foreign | df_eval["merchant"].astype(str).str.contains(
                pattern, case=False, na=False, regex=True
            )
        apply(is_foreign, 25.0, "foreign/online merchant")

        # Rule 4: card-testing sized charge (up to about USD 5) at a merchant
        # that is new or foreign (+25). Small purchases at known local shops
        # are normal and are not penalized.
        usd = number("amount_usd_equiv")
        is_micro = (usd > 0.0) & (usd <= MICRO_AMOUNT_USD) & (is_new | is_foreign)
        apply(is_micro, 25.0, "micro-amount test charge")

        # Rule 5: amount far above the usual (z-score > 3) (+30)
        apply(zscore > 3.0, 30.0, "unusually large amount")

        # Rule 6: new merchant and a large amount together (+50)
        apply(is_new & (zscore > 2.5), 50.0, "large amount at new merchant")

        df_eval["rule_risk_score"] = np.clip(rule_scores, 0.0, 100.0)
        df_eval["reasons"] = reasons

        if "risk_score" in df_eval.columns:
            ml_score = pd.to_numeric(df_eval["risk_score"], errors="coerce").fillna(0.0)
            df_eval["final_risk_score"] = np.round(
                ml_score * self.ml_weight + df_eval["rule_risk_score"] * self.rules_weight,
                2,
            )
        else:
            df_eval["final_risk_score"] = df_eval["rule_risk_score"]

        df_eval["is_high_risk"] = df_eval["final_risk_score"] >= self.risk_threshold
        return df_eval
