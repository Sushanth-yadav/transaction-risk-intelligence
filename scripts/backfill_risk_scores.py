import os
import sys

# Add the RazorGuard project root to Python's import path.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from apps.transactions.models import Transaction
from apps.risk.models import RiskAssessment
from apps.risk.services import run_risk_pipeline


def main():
    transactions = Transaction.objects.all().order_by("created_at")

    total = transactions.count()
    processed = 0
    skipped = 0
    failed = 0

    print(f"Found {total} transactions.")

    for transaction in transactions:
        try:
            # Don't process a transaction twice.
            if RiskAssessment.objects.filter(transaction=transaction).exists():
                skipped += 1
                continue

            run_risk_pipeline(transaction)

            processed += 1

            if processed % 50 == 0:
                print(
                    f"Processed {processed}/{total} "
                    f"(skipped={skipped}, failed={failed})"
                )

        except Exception as exc:
            failed += 1
            print(
                f"FAILED: {transaction.transaction_id} "
                f"-> {type(exc).__name__}: {exc}"
            )

    print("\nBackfill complete.")
    print(f"Total transactions : {total}")
    print(f"Processed           : {processed}")
    print(f"Skipped             : {skipped}")
    print(f"Failed              : {failed}")


if __name__ == "__main__":
    main()