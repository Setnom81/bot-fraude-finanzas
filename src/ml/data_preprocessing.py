import re

import numpy as np
import pandas as pd

from src.config import LOCAL_TZ, MIN_HISTORY_FOR_ZSCORE, USD_TO_CRC_RATE

# BAC puts the location after the merchant name:
#   "ABASTECEDOR 3A Ciudad y país: SAN JOSE, Costa Rica"
_LOCATION_SPLIT = re.compile(r"\s*Ciudad y pa\S{1,2}s\s*:\s*", re.IGNORECASE)

# The email subject carries the purchase time in bank-local time:
#   "Notificación de transacción AIRBNB * 24-02-2026 - 22:20"
_SUBJECT_DATETIME = re.compile(r"(\d{2})-(\d{2})-(\d{4})\s*-\s*(\d{2}):(\d{2})")

HOME_COUNTRY = "costa rica"

# Charges this close together count as one burst.
BURST_WINDOW = pd.Timedelta(minutes=10)

# A merchant keeps counting as "new" for this long after its first charge,
# so the 2nd, 3rd... charge of a fraud run is not treated as a known shop.
NEW_MERCHANT_WINDOW = pd.Timedelta(hours=24)


def split_merchant(raw) -> tuple[str, str]:
    """Splits the stored merchant text into (normalized name, location)."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return "", ""
    parts = _LOCATION_SPLIT.split(str(raw), maxsplit=1)
    name = " ".join(parts[0].split()).upper()
    location = parts[1].strip() if len(parts) > 1 else ""
    return name, location


def is_foreign_location(location: str) -> bool:
    """True when a location is present and its country is not the home country.

    An absent location is treated as unknown, not foreign.
    """
    if not location:
        return False
    country = location.rsplit(",", 1)[-1].strip().lower()
    return country != HOME_COUNTRY


def subject_local_datetime(subject) -> pd.Timestamp:
    """Extracts the bank-local purchase time from the email subject, or NaT."""
    match = _SUBJECT_DATETIME.search(str(subject or ""))
    if not match:
        return pd.NaT
    day, month, year, hour, minute = match.groups()
    return pd.to_datetime(
        f"{year}-{month}-{day} {hour}:{minute}",
        format="%Y-%m-%d %H:%M",
        errors="coerce",
    )


class DataPreprocessor:
    """Feature engineering for the anomaly model and the rule engine.

    Every feature of a transaction is computed only from transactions that
    happened before it, so training and live scoring see the same thing.
    """

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Adds feature columns to a transactions DataFrame.

        Rows are returned in the same order (and with the same index) as given.
        """
        if df.empty:
            return pd.DataFrame()

        out = df.copy()
        out["_orig_pos"] = np.arange(len(out))

        # -----------------------------------------------------------------
        # 1. Time: arrival order (UTC) and purchase time in the local zone
        # -----------------------------------------------------------------
        if "email_date" in out.columns:
            email_utc = pd.to_datetime(
                out["email_date"], errors="coerce", utc=True, format="mixed"
            )
        else:
            email_utc = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")

        email_local = email_utc.dt.tz_convert(LOCAL_TZ).dt.tz_localize(None)

        if "email_subject" in out.columns:
            subject_local = out["email_subject"].map(subject_local_datetime)
            subject_local = pd.to_datetime(subject_local, errors="coerce")
        else:
            subject_local = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns]")

        local_time = subject_local.fillna(email_local)
        out["local_time"] = local_time

        order_key = email_utc.dt.tz_localize(None).fillna(local_time)
        out["_order"] = order_key
        out = out.sort_values("_order", kind="stable", na_position="last")

        out["hour"] = out["local_time"].dt.hour.fillna(-1).astype(int)
        out["day_of_week"] = out["local_time"].dt.dayofweek.fillna(-1).astype(int)
        out["is_weekend"] = out["day_of_week"].isin([5, 6]).astype(int)
        out["is_night_transaction"] = out["hour"].between(0, 5).astype(int)

        # -----------------------------------------------------------------
        # 2. Merchant: normalized name, location, novelty
        # -----------------------------------------------------------------
        if "merchant" in out.columns:
            split = out["merchant"].map(split_merchant)
            out["merchant_name"] = split.map(lambda pair: pair[0])
            out["merchant_location"] = split.map(lambda pair: pair[1])
        else:
            out["merchant_name"] = ""
            out["merchant_location"] = ""

        out["is_foreign"] = out["merchant_location"].map(is_foreign_location).astype(int)
        out["merchant_tx_count_so_far"] = out.groupby("merchant_name").cumcount()
        out["is_new_merchant"] = (out["merchant_tx_count_so_far"] == 0).astype(int)
        # Log scale, so a favourite shop's ever-growing count does not drift
        # outside what the model saw in training.
        out["merchant_tx_count_log"] = np.log1p(out["merchant_tx_count_so_far"])

        # Velocity: earlier charges within the burst window (any merchant),
        # and whether this merchant was first seen very recently.
        times = out["_order"].to_numpy(dtype="datetime64[ns]")
        has_time = ~np.isnat(times)
        positions = np.arange(len(out))
        window_start = np.searchsorted(
            times[has_time], times[has_time] - BURST_WINDOW.to_timedelta64(), side="left"
        )
        recent = np.zeros(len(out), dtype=int)
        recent[has_time] = positions[has_time] - window_start
        out["recent_tx_count"] = recent

        first_seen = out.groupby("merchant_name")["_order"].transform("min")
        merchant_age = out["_order"] - first_seen
        out["is_recent_merchant"] = (
            (out["is_new_merchant"] == 1) | (merchant_age < NEW_MERCHANT_WINDOW)
        ).astype(int)

        # -----------------------------------------------------------------
        # 3. Amount on a single scale (CRC)
        # -----------------------------------------------------------------
        amount = pd.Series(np.nan, index=out.index, dtype="float64")
        if "amount_value" in out.columns:
            amount = pd.to_numeric(out["amount_value"], errors="coerce").astype("float64")
        if "amount" in out.columns:
            parsed = pd.to_numeric(
                out["amount"]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.extract(r"(\d*\.?\d+)")[0],
                errors="coerce",
            )
            amount = amount.fillna(parsed)
        amount = amount.fillna(0.0)

        if "currency" in out.columns:
            is_usd = out["currency"].astype(str).str.upper().eq("USD")
        else:
            is_usd = pd.Series(False, index=out.index)

        out["amount_num"] = amount
        out["amount_crc"] = np.where(is_usd, amount * USD_TO_CRC_RATE, amount)
        out["amount_usd_equiv"] = out["amount_crc"] / USD_TO_CRC_RATE
        out["amount_log"] = np.log1p(out["amount_crc"])

        # -----------------------------------------------------------------
        # 4. Deviation from what came before
        # -----------------------------------------------------------------
        a = out["amount_crc"]
        prior_count = np.arange(len(out))
        prior_mean = a.expanding().mean().shift(1)
        prior_std = a.expanding().std().shift(1)
        usable = (prior_count >= MIN_HISTORY_FOR_ZSCORE) & (prior_std > 0)
        zscore = (a - prior_mean) / prior_std.where(prior_std > 0)
        out["amount_zscore"] = np.where(usable, zscore, 0.0)
        out["amount_zscore"] = out["amount_zscore"].fillna(0.0)

        merchant_prior_sum = out.groupby("merchant_name")["amount_crc"].cumsum() - a
        merchant_prior_n = out["merchant_tx_count_so_far"]
        merchant_prior_mean = merchant_prior_sum / merchant_prior_n.where(merchant_prior_n > 0)
        ratio = a / merchant_prior_mean.where(merchant_prior_mean > 0)
        out["ratio_to_merchant_avg"] = ratio.fillna(1.0)

        out = out.sort_values("_orig_pos", kind="stable")
        return out.drop(columns=["_orig_pos", "_order"])

    def get_feature_columns(self) -> list[str]:
        """Numeric feature columns used by the anomaly model."""
        return [
            "amount_log",
            "hour",
            "day_of_week",
            "is_weekend",
            "is_night_transaction",
            "is_foreign",
            "is_new_merchant",
            "merchant_tx_count_log",
            "recent_tx_count",
            "amount_zscore",
            "ratio_to_merchant_avg",
        ]
