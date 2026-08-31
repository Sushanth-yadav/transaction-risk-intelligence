"""
RazorGuard synthetic data generator.

Generates a realistic (but entirely synthetic) financial transaction dataset
with entity relationships (customer, device, IP, merchant, payment instrument)
and four injected fraud patterns:

  1. account_takeover   - new device + new location + high amount, sudden
  2. card_testing        - burst of small rapid transactions
  3. fraud_ring          - cluster of unrelated customers sharing a device/IP
  4. first_time_high_value - dormant/new account, one large off-profile txn

No real personal or financial data is used anywhere in this project.

Usage:
    python generate_synthetic_data.py --customers 2000 --out ../data/raw/transactions.csv
"""

import argparse
import random
import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

RNG_SEED = 42

LOCATIONS = [
    "Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai", "Pune",
    "Kolkata", "Ahmedabad", "Jaipur", "Lucknow", "Kochi", "Chandigarh",
]

MERCHANT_CATEGORIES = [
    "grocery", "electronics", "travel", "food_delivery", "utilities",
    "fashion", "entertainment", "fuel", "pharmacy", "jewelry",
]

PAYMENT_METHODS = ["card", "upi", "netbanking", "wallet"]


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class Customer:
    """A synthetic customer with a stable behavioral profile."""

    def __init__(self, rng: random.Random, np_rng: np.random.Generator):
        self.customer_id = make_id("cust")
        self.account_age_days = int(np_rng.exponential(400)) + 1
        self.home_location = rng.choice(LOCATIONS)
        # log-normal spend profile -> realistic skew (most customers modest, few big spenders)
        self.avg_amount = float(np.clip(np_rng.lognormal(mean=6.5, sigma=0.7), 100, 50000))
        self.preferred_hours = sorted(rng.sample(range(24), k=rng.randint(4, 8)))
        self.devices = [make_id("dev") for _ in range(rng.randint(1, 2))]
        self.ips = [make_id("ip") for _ in range(rng.randint(1, 2))]
        self.instruments = [make_id("pmt") for _ in range(rng.randint(1, 2))]
        self.preferred_methods = rng.sample(PAYMENT_METHODS, k=rng.randint(1, 2))
        self.txn_count = 0
        self.failed_attempts = 0


def sample_amount(rng: np.random.Generator, avg: float) -> float:
    val = rng.lognormal(mean=np.log(max(avg, 50)), sigma=0.4)
    return round(float(np.clip(val, 10, 500000)), 2)


def sample_timestamp(rng: random.Random, start: datetime, days_span: int, preferred_hours) -> datetime:
    day_offset = rng.randint(0, days_span - 1)
    if rng.random() < 0.75 and preferred_hours:
        hour = rng.choice(preferred_hours)
    else:
        hour = rng.randint(0, 23)
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    return start + timedelta(days=day_offset, hours=hour, minutes=minute, seconds=second)


def generate(n_customers: int, avg_txns_per_customer: int, days_span: int, fraud_rate: float, seed: int = RNG_SEED):
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    start = datetime(2026, 1, 1)

    customers = [Customer(rng, np_rng) for _ in range(n_customers)]
    merchants = [make_id("merch") for _ in range(max(50, n_customers // 20))]
    merchant_category = {m: rng.choice(MERCHANT_CATEGORIES) for m in merchants}

    rows = []

    # ---- 1. Legitimate transactions, sampled around each customer's profile ----
    for cust in customers:
        n_txns = max(1, int(np_rng.poisson(avg_txns_per_customer)))
        for _ in range(n_txns):
            ts = sample_timestamp(rng, start, days_span, cust.preferred_hours)
            amount = sample_amount(np_rng, cust.avg_amount)
            cust.txn_count += 1
            rows.append({
                "transaction_id": make_id("txn"),
                "customer_id": cust.customer_id,
                "merchant_id": rng.choice(merchants),
                "device_id": rng.choice(cust.devices),
                "ip_id": rng.choice(cust.ips),
                "payment_instrument_id": rng.choice(cust.instruments),
                "amount": amount,
                "timestamp": ts,
                "location": cust.home_location if rng.random() < 0.9 else rng.choice(LOCATIONS),
                "payment_method": rng.choice(cust.preferred_methods),
                "account_age_days": cust.account_age_days,
                "customer_avg_amount": round(cust.avg_amount, 2),
                "fraud_label": 0,
                "fraud_pattern": "none",
            })

    legit_count = len(rows)
    n_fraud = int(legit_count * fraud_rate / (1 - fraud_rate))
    patterns = ["account_takeover", "card_testing", "fraud_ring", "first_time_high_value"]
    per_pattern = max(1, n_fraud // len(patterns))

    # ---- 1b. hard-negative legitimate transactions: look mildly suspicious but ARE legit ----
    # (new device from a phone upgrade, travel to a new city, an occasional bigger purchase)
    n_hard_negatives = int(legit_count * 0.04)
    for _ in range(n_hard_negatives):
        cust = rng.choice(customers)
        ts = sample_timestamp(rng, start, days_span, None)
        variant = rng.choice(["new_device", "new_location", "bigger_purchase"])
        device = make_id("dev") if variant == "new_device" else rng.choice(cust.devices)
        location = rng.choice(LOCATIONS) if variant == "new_location" else cust.home_location
        amount = sample_amount(np_rng, cust.avg_amount * (rng.uniform(2, 4) if variant == "bigger_purchase" else 1))
        rows.append({
            "transaction_id": make_id("txn"),
            "customer_id": cust.customer_id,
            "merchant_id": rng.choice(merchants),
            "device_id": device,
            "ip_id": rng.choice(cust.ips),
            "payment_instrument_id": rng.choice(cust.instruments),
            "amount": amount,
            "timestamp": ts,
            "location": location,
            "payment_method": rng.choice(cust.preferred_methods),
            "account_age_days": cust.account_age_days,
            "customer_avg_amount": round(cust.avg_amount, 2),
            "fraud_label": 0,
            "fraud_pattern": "none",
        })

    # ---- 2. account_takeover: 1-3 of {new device, new ip, new location, amount jump} fire, not always all ----
    for _ in range(per_pattern):
        cust = rng.choice(customers)
        ts = sample_timestamp(rng, start, days_span, None)
        signals = rng.sample(["device", "ip", "location", "amount"], k=rng.randint(2, 4))
        device = make_id("dev") if "device" in signals else rng.choice(cust.devices)
        ip = make_id("ip") if "ip" in signals else rng.choice(cust.ips)
        location = rng.choice([l for l in LOCATIONS if l != cust.home_location]) if "location" in signals else cust.home_location
        amount_mult = rng.uniform(3, 9) if "amount" in signals else rng.uniform(1.2, 3)
        rows.append({
            "transaction_id": make_id("txn"),
            "customer_id": cust.customer_id,
            "merchant_id": rng.choice(merchants),
            "device_id": device,
            "ip_id": ip,
            "payment_instrument_id": rng.choice(cust.instruments),
            "amount": round(cust.avg_amount * amount_mult, 2),
            "timestamp": ts,
            "location": location,
            "payment_method": rng.choice(PAYMENT_METHODS),
            "account_age_days": cust.account_age_days,
            "customer_avg_amount": round(cust.avg_amount, 2),
            "fraud_label": 1,
            "fraud_pattern": "account_takeover",
        })

    # ---- 3. card_testing: burst of small rapid transactions ----
    for _ in range(per_pattern // 4 or 1):
        cust = rng.choice(customers)
        base_ts = sample_timestamp(rng, start, days_span, None)
        device = make_id("dev")
        ip = make_id("ip")
        burst_size = rng.randint(4, 8)
        for i in range(burst_size):
            rows.append({
                "transaction_id": make_id("txn"),
                "customer_id": cust.customer_id,
                "merchant_id": rng.choice(merchants),
                "device_id": device,
                "ip_id": ip,
                "payment_instrument_id": rng.choice(cust.instruments),
                "amount": round(rng.uniform(10, 150), 2),
                "timestamp": base_ts + timedelta(seconds=i * rng.randint(15, 90)),
                "location": cust.home_location,
                "payment_method": "card",
                "account_age_days": cust.account_age_days,
                "customer_avg_amount": round(cust.avg_amount, 2),
                "fraud_label": 1,
                "fraud_pattern": "card_testing",
            })

    # ---- 4. fraud_ring: cluster of otherwise-unrelated customers sharing a device/IP ----
    n_rings = max(1, per_pattern // 4)
    for _ in range(n_rings):
        ring_device = make_id("dev")
        ring_ip = make_id("ip")
        ring_customers = rng.sample(customers, k=rng.randint(3, 5))
        for cust in ring_customers:
            ts = sample_timestamp(rng, start, days_span, None)
            rows.append({
                "transaction_id": make_id("txn"),
                "customer_id": cust.customer_id,
                "merchant_id": rng.choice(merchants),
                "device_id": ring_device,
                "ip_id": ring_ip,
                "payment_instrument_id": rng.choice(cust.instruments),
                "amount": round(cust.avg_amount * rng.uniform(1.5, 5), 2),
                "timestamp": ts,
                "location": rng.choice(LOCATIONS),
                "payment_method": rng.choice(PAYMENT_METHODS),
                "account_age_days": cust.account_age_days,
                "customer_avg_amount": round(cust.avg_amount, 2),
                "fraud_label": 1,
                "fraud_pattern": "fraud_ring",
            })

    # ---- 5. first_time_high_value: dormant/new account, one large off-profile txn ----
    for _ in range(per_pattern):
        cust = rng.choice(customers)
        ts = sample_timestamp(rng, start, days_span, None)
        rows.append({
            "transaction_id": make_id("txn"),
            "customer_id": cust.customer_id,
            "merchant_id": rng.choice(merchants),
            "device_id": rng.choice(cust.devices),
            "ip_id": rng.choice(cust.ips),
            "payment_instrument_id": rng.choice(cust.instruments),
            "amount": round(max(cust.avg_amount * rng.uniform(4, 12), 8000), 2),
            "timestamp": ts,
            "location": cust.home_location,
            "payment_method": rng.choice(PAYMENT_METHODS),
            "account_age_days": min(cust.account_age_days, rng.randint(0, 45)),
            "customer_avg_amount": round(cust.avg_amount, 2),
            "fraud_label": 1,
            "fraud_pattern": "first_time_high_value",
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("timestamp").reset_index(drop=True)

    # merchant category as a column (not fraud-informative on its own, just realism)
    df["merchant_category"] = df["merchant_id"].map(merchant_category)

    return df, {"n_customers": len(customers), "n_merchants": len(merchants)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--customers", type=int, default=2000)
    parser.add_argument("--avg-txns-per-customer", type=int, default=9)
    parser.add_argument("--days-span", type=int, default=120)
    parser.add_argument("--fraud-rate", type=float, default=0.025)
    parser.add_argument("--seed", type=int, default=RNG_SEED)
    parser.add_argument("--out", type=str, default="../data/raw/transactions.csv")
    args = parser.parse_args()

    df, meta = generate(
        n_customers=args.customers,
        avg_txns_per_customer=args.avg_txns_per_customer,
        days_span=args.days_span,
        fraud_rate=args.fraud_rate,
        seed=args.seed,
    )

    df.to_csv(args.out, index=False)

    print(f"Generated {len(df)} transactions for {meta['n_customers']} customers, "
          f"{meta['n_merchants']} merchants.")
    print(f"Fraud rate: {df['fraud_label'].mean():.4%}")
    print(df["fraud_pattern"].value_counts())
    print(f"Saved to: {args.out}")


if __name__ == "__main__":
    main()
