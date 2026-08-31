"""
Seed the database from ml/data/raw/transactions.csv.

Loads transactions in chronological order via the ORM directly (not
through the risk-scoring API) so we get a populated transaction history
fast, without re-running RandomForest inference ~19k times. Risk scoring
for these historical rows can be backfilled separately with
scripts/backfill_risk_scores.py once you want scored data in the dashboard.

Usage (from project root, with .env configured and migrations applied):
    python scripts/seed_db.py [--limit N]
"""

import argparse
import os
import sys
from pathlib import Path

import django
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.transactions.models import Customer, Device, IPAddress, Merchant, PaymentInstrument, Transaction  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=str(BASE_DIR / "ml" / "data" / "raw" / "transactions.csv"))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    df = pd.read_csv(args.csv, parse_dates=["timestamp"]).sort_values("timestamp")
    if args.limit:
        df = df.head(args.limit)

    customer_cache, merchant_cache, device_cache, ip_cache, instrument_cache = {}, {}, {}, {}, {}

    created = 0
    for _, row in df.iterrows():
        if row["customer_id"] not in customer_cache:
            customer_cache[row["customer_id"]], _ = Customer.objects.get_or_create(
                customer_id=row["customer_id"],
                defaults={
                    "account_age_days": int(row["account_age_days"]),
                    "avg_amount": row["customer_avg_amount"],
                    "home_location": row["location"],
                },
            )
        if row["merchant_id"] not in merchant_cache:
            merchant_cache[row["merchant_id"]], _ = Merchant.objects.get_or_create(
                merchant_id=row["merchant_id"], defaults={"category": row["merchant_category"]}
            )
        if row["device_id"] not in device_cache:
            device_cache[row["device_id"]], _ = Device.objects.get_or_create(device_id=row["device_id"])
        if row["ip_id"] not in ip_cache:
            ip_cache[row["ip_id"]], _ = IPAddress.objects.get_or_create(ip_id=row["ip_id"])
        if row["payment_instrument_id"] not in instrument_cache:
            instrument_cache[row["payment_instrument_id"]], _ = PaymentInstrument.objects.get_or_create(
                instrument_id=row["payment_instrument_id"]
            )

        _, was_created = Transaction.objects.get_or_create(
            transaction_id=row["transaction_id"],
            defaults={
                "customer": customer_cache[row["customer_id"]],
                "merchant": merchant_cache[row["merchant_id"]],
                "device": device_cache[row["device_id"]],
                "ip_address": ip_cache[row["ip_id"]],
                "payment_instrument": instrument_cache[row["payment_instrument_id"]],
                "amount": row["amount"],
                "timestamp": row["timestamp"],
                "location": row["location"],
                "payment_method": row["payment_method"],
                "fraud_label": int(row["fraud_label"]),
            },
        )
        if was_created:
            created += 1

    print(f"Seeded {created} transactions ({len(df)} rows processed) from {args.csv}")


if __name__ == "__main__":
    main()
