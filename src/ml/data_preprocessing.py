import numpy as np
import pandas as pd


class DataPreprocessor:
    """
    Data Preprocessing and Feature Engineering pipeline for anomaly detection models.
    Transforms raw SQL transaction payloads into numeric feature matrices.
    """

    def __init__(self):
        pass

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Executes full preprocessing and feature extraction pipeline.

        Args:
            df (pd.DataFrame): Raw transactions DataFrame from storage.

        Returns:
            pd.DataFrame: Processed DataFrame containing engineered numeric features.
        """
        if df.empty:
            return pd.DataFrame()

        df_processed = df.copy()

        # ---------------------------------------------------------
        # 1. Datetime Consolidation
        # ---------------------------------------------------------
        date_fallback_col = next(
            (col for col in ["email_date", "received_at", "created_at"] if col in df_processed.columns), 
            None
        )

        if "transaction_date" in df_processed.columns:
            df_processed["transaction_date"] = pd.to_datetime(
                df_processed["transaction_date"], 
                errors="coerce", 
                dayfirst=True, 
                format="mixed",
                utc=True
            )
            
            if date_fallback_col:
                df_processed[date_fallback_col] = pd.to_datetime(
                    df_processed[date_fallback_col], 
                    errors="coerce", 
                    dayfirst=True, 
                    format="mixed",
                    utc=True
                )
                df_processed["transaction_date"] = df_processed["transaction_date"].fillna(
                    df_processed[date_fallback_col]
                )
        elif date_fallback_col:
            df_processed["transaction_date"] = pd.to_datetime(
                df_processed[date_fallback_col], 
                errors="coerce", 
                dayfirst=True, 
                format="mixed",
                utc=True
            )

        # Ensure strict chronological order for sequential features
        original_index = df_processed.index
        if "transaction_date" in df_processed.columns and pd.api.types.is_datetime64_any_dtype(df_processed["transaction_date"]):
            df_processed = df_processed.sort_values(by="transaction_date", ascending=True)

        # ---------------------------------------------------------
        # 2. Temporal Features Extraction
        # ---------------------------------------------------------
        if "transaction_date" in df_processed.columns and pd.api.types.is_datetime64_any_dtype(df_processed["transaction_date"]):
            df_processed["hour"] = df_processed["transaction_date"].dt.hour.fillna(-1)
            df_processed["day_of_week"] = df_processed["transaction_date"].dt.dayofweek.fillna(-1)
            df_processed["is_weekend"] = df_processed["day_of_week"].isin([5, 6]).astype(int)
            df_processed["is_night_transaction"] = df_processed["hour"].between(0, 5).astype(int)
        else:
            df_processed["hour"] = -1
            df_processed["day_of_week"] = -1
            df_processed["is_weekend"] = 0
            df_processed["is_night_transaction"] = 0

        # ---------------------------------------------------------
        # 3. Merchant Novelty & Historical Frequency (NEW 🌟)
        # ---------------------------------------------------------
        if "merchant" in df_processed.columns:
            # Cumulative count of occurrences per merchant up to this point in time
            df_processed["merchant_tx_count_so_far"] = df_processed.groupby("merchant").cumcount()
            # Flag indicating first time buying at this specific merchant
            df_processed["is_new_merchant"] = (df_processed["merchant_tx_count_so_far"] == 0).astype(int)
        else:
            df_processed["merchant_tx_count_so_far"] = 0
            df_processed["is_new_merchant"] = 0

        # ---------------------------------------------------------
        # 4. Amount Scaling & Transformation
        # ---------------------------------------------------------
        if "amount" in df_processed.columns:
            cleaned_amount = (
                df_processed["amount"]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.extract(r"(\d+\.?\d*)")[0]
            )
            df_processed["amount"] = pd.to_numeric(cleaned_amount, errors="coerce").fillna(0.0)
            df_processed["amount_log"] = np.log1p(df_processed["amount"])
        else:
            df_processed["amount"] = 0.0
            df_processed["amount_log"] = 0.0

        # ---------------------------------------------------------
        # 5. Behavioral & Deviation Features
        # ---------------------------------------------------------
        user_mean = df_processed["amount"].mean()
        user_std = df_processed["amount"].std()
        
        if user_std and user_std > 0:
            df_processed["amount_zscore"] = (df_processed["amount"] - user_mean) / user_std
        else:
            df_processed["amount_zscore"] = 0.0

        if "merchant" in df_processed.columns:
            merchant_means = df_processed.groupby("merchant")["amount"].transform("mean")
            df_processed["ratio_to_merchant_avg"] = np.where(
                merchant_means > 0, df_processed["amount"] / merchant_means, 1.0
            )
        else:
            df_processed["ratio_to_merchant_avg"] = 1.0

        # Restore original index order before returning
        return df_processed.reindex(original_index)

    def get_feature_columns(self) -> list[str]:
        """
        Returns list of numerical feature column names required for model training.
        """
        return [
            "amount_log",
            "hour",
            "day_of_week",
            "is_weekend",
            "is_night_transaction",
            "is_new_merchant",               # High predictive weight for novel merchants
            "merchant_tx_count_so_far",      # Historical frequency
            "amount_zscore",
            "ratio_to_merchant_avg",
        ]