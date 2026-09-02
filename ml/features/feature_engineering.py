"""
RazorGuard feature engineering.

All "historical" features (customer averages, velocity, novelty flags, device
sharing) are computed CAUSALLY: for transaction i, only transactions with an
earlier timestamp for the same customer/device are used. This prevents
train/serve skew and future-leakage into offline evaluation metrics.

This module is intended to be shared between:
  - offline batch training (ml/training/*)
  - the live risk-scoring service (apps/risk) — which will call an
    equivalent per-transaction version backed by the database instead of a
    full CSV, but using the same feature *definitions* as documented here.
"""

import numpy as np
import pandas as pd
from pathlib import Path

EPS = 1e-6


def _expanding_customer_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Per-customer expanding mean/std of amount, computed BEFORE current row."""
    df = df.sort_values(["customer_id", "timestamp"]).copy()
    grp = df.groupby("customer_id")["amount"]

    # shift(1) so the current transaction's own amount is excluded
    df["hist_amount_mean"] = grp.apply(lambda s: s.expanding().mean().shift(1)).reset_index(level=0, drop=True)
    df["hist_amount_std"] = grp.apply(lambda s: s.expanding().std().shift(1)).reset_index(level=0, drop=True)
    df["customer_txn_count_before"] = grp.cumcount()

    # for customers with no prior history, fall back to the declared
    # customer_avg_amount (their long-run profile) rather than NaN
    df["hist_amount_mean"] = df["hist_amount_mean"].fillna(df["customer_avg_amount"])
    df["hist_amount_std"] = df["hist_amount_std"].fillna(df["customer_avg_amount"] * 0.3)
    fallback_std = df["customer_avg_amount"] * 0.1 + EPS
    df["hist_amount_std"] = np.where(df["hist_amount_std"] == 0, fallback_std, df["hist_amount_std"])

    return df


def _novelty_flags(df: pd.DataFrame) -> pd.DataFrame:
    """is_new_device / is_new_ip / is_new_location: first time seen for this customer, causal."""
    df = df.sort_values(["customer_id", "timestamp"]).copy()

    for col, out in [("device_id", "is_new_device"), ("ip_id", "is_new_ip"), ("location", "is_new_location")]:
        seen = {}
        flags = np.zeros(len(df), dtype=int)
        for pos, (cust, val) in enumerate(zip(df["customer_id"].values, df[col].values)):
            key = (cust, val)
            if key not in seen:
                flags[pos] = 1
                seen[key] = True
            else:
                flags[pos] = 0
        df[out] = flags
    return df


def _velocity_features(df: pd.DataFrame) -> pd.DataFrame:
    """txn_count_last_1h / _24h and hours_since_last_txn, causal per customer."""
    df = df.sort_values(["customer_id", "timestamp"]).copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    hours_since = []
    count_1h = []
    count_24h = []

    for cust, group in df.groupby("customer_id", sort=False):
        times = group["timestamp"].values.astype("datetime64[s]")
        n = len(times)
        prev_time = None
        window = []  # list of prior timestamps within this customer's history
        for i in range(n):
            t = times[i]
            if prev_time is None:
                hours_since.append(np.nan)
            else:
                hours_since.append((t - prev_time) / np.timedelta64(1, "h"))
            # counts of PRIOR transactions within lookback windows
            c1h = sum(1 for pt in window if (t - pt) / np.timedelta64(1, "h") <= 1)
            c24h = sum(1 for pt in window if (t - pt) / np.timedelta64(1, "h") <= 24)
            count_1h.append(c1h)
            count_24h.append(c24h)
            window.append(t)
            prev_time = t

    df["hours_since_last_txn"] = hours_since
    df["txn_count_last_1h"] = count_1h
    df["txn_count_last_24h"] = count_24h
    # first-ever transaction: no prior activity -> treat as "long gap"
    df["hours_since_last_txn"] = df["hours_since_last_txn"].fillna(9999)
    return df


def _device_sharing_feature(df: pd.DataFrame) -> pd.DataFrame:
    """device_customer_count_so_far: distinct customers seen on this device up to (excluding) this txn."""
    df = df.sort_values("timestamp").copy()
    seen_customers_per_device = {}
    counts = np.zeros(len(df), dtype=int)
    for pos, (dev, cust) in enumerate(zip(df["device_id"].values, df["customer_id"].values)):
        s = seen_customers_per_device.setdefault(dev, set())
        counts[pos] = len(s - {cust}) if cust in s else len(s)
        s.add(cust)
    df["device_customer_count_so_far"] = counts
    return df


def build_features(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Main entry point. Takes the raw transaction dataframe and returns a
    feature-engineered dataframe (original columns preserved + new feature
    columns), sorted back to chronological order.
    """
    df = raw_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    df = _expanding_customer_stats(df)
    df = _novelty_flags(df)
    df = _velocity_features(df)
    df = _device_sharing_feature(df)

    df["amount_zscore_vs_customer"] = (df["amount"] - df["hist_amount_mean"]) / (df["hist_amount_std"] + EPS)
    df["amount_ratio_to_customer_avg"] = df["amount"] / (df["hist_amount_mean"] + EPS)

    df["hour_of_day"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek

    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


FEATURE_COLUMNS = [
    "amount",
    "amount_zscore_vs_customer",
    "amount_ratio_to_customer_avg",
    "customer_txn_count_before",
    "is_new_device",
    "is_new_ip",
    "is_new_location",
    "hours_since_last_txn",
    "txn_count_last_1h",
    "txn_count_last_24h",
    "device_customer_count_so_far",
    "account_age_days",
    "hour_of_day",
    "day_of_week",
]

CATEGORICAL_COLUMNS = ["payment_method", "merchant_category"]


if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parent.parent
    RAW_PATH = BASE_DIR / "data" / "raw" / "transactions.csv"
    PROCESSED_DIR = BASE_DIR / "data" / "processed"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH = PROCESSED_DIR / "features.csv"

    raw = pd.read_csv(RAW_PATH)
    features = build_features(raw)
    features.to_csv(OUTPUT_PATH, index=False)

    print(
        f"Built {len(FEATURE_COLUMNS)} numeric features + "
        f"{len(CATEGORICAL_COLUMNS)} categorical, "
        f"{len(features)} rows -> {OUTPUT_PATH}"
    )
    print(features[FEATURE_COLUMNS + ["fraud_label"]].describe().T)