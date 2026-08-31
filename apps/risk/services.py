"""
Risk scoring service.

This is the live-scoring counterpart to ml/training/train_and_evaluate.py.
It must compute features using the EXACT SAME DEFINITIONS as
ml/features/feature_engineering.py, but sourced from the database (only
transactions with an earlier timestamp for this customer) instead of a
static CSV - this is what makes the features "causal" at serving time too,
matching how they were computed for training.

Day 1 scope: ML sub-score only, wired end-to-end through the API.
Day 2 will add rule_score, behavioral_score, and graph_score into the
aggregation (see apps.risk.aggregator, added on Day 2).
"""

import sys
from datetime import timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd
from django.conf import settings

sys.path.append(str(Path(settings.BASE_DIR) / "ml" / "features"))
from feature_engineering import FEATURE_COLUMNS, CATEGORICAL_COLUMNS  # noqa: E402


@lru_cache(maxsize=1)
def _load_model():
    """Load the trained RandomForest pipeline once per process."""
    model_path = settings.ML_MODELS_DIR / "random_forest.joblib"
    if not model_path.exists():
        raise FileNotFoundError(
            f"No trained model found at {model_path}. Run "
            "ml/training/train_and_evaluate.py first."
        )
    return joblib.load(model_path)


def compute_live_features(transaction) -> dict:
    """
    Compute the same feature set as training, using only transactions that
    happened strictly BEFORE this one for the same customer (or, for
    device-sharing, strictly before this one globally) - this is the
    causal constraint that prevents train/serve skew.
    """
    customer = transaction.customer
    prior_qs = (
        customer.transactions
        .filter(timestamp__lt=transaction.timestamp)
        .order_by("timestamp")
    )
    prior = list(prior_qs.values("amount", "timestamp", "device_id", "ip_address_id", "location"))

    amounts = [float(p["amount"]) for p in prior]
    if amounts:
        hist_mean = sum(amounts) / len(amounts)
        hist_std = (sum((a - hist_mean) ** 2 for a in amounts) / len(amounts)) ** 0.5
    else:
        hist_mean = float(customer.avg_amount) or 1.0
        hist_std = hist_mean * 0.3

    hist_std = hist_std if hist_std > 0 else (float(customer.avg_amount) * 0.1 + 1e-6)

    amount = float(transaction.amount)
    amount_zscore = (amount - hist_mean) / (hist_std + 1e-6)
    amount_ratio = amount / (hist_mean + 1e-6)

    customer_txn_count_before = len(prior)

    seen_devices = {p["device_id"] for p in prior}
    seen_ips = {p["ip_address_id"] for p in prior}
    seen_locations = {p["location"] for p in prior}
    is_new_device = int(transaction.device_id not in seen_devices)
    is_new_ip = int(transaction.ip_address_id not in seen_ips)
    is_new_location = int(transaction.location not in seen_locations)

    if prior:
        last_ts = prior[-1]["timestamp"]
        hours_since_last = (transaction.timestamp - last_ts).total_seconds() / 3600
        cutoff_1h = transaction.timestamp - timedelta(hours=1)
        cutoff_24h = transaction.timestamp - timedelta(hours=24)
        txn_count_last_1h = sum(1 for p in prior if p["timestamp"] >= cutoff_1h)
        txn_count_last_24h = sum(1 for p in prior if p["timestamp"] >= cutoff_24h)
    else:
        hours_since_last = 9999
        txn_count_last_1h = 0
        txn_count_last_24h = 0

    # device sharing across customers, up to (excluding) this transaction
    from apps.transactions.models import Transaction as TransactionModel
    device_customer_count = (
        TransactionModel.objects
        .filter(device=transaction.device, timestamp__lt=transaction.timestamp)
        .exclude(customer=customer)
        .values("customer_id").distinct().count()
    )

    return {
        "amount": amount,
        "amount_zscore_vs_customer": amount_zscore,
        "amount_ratio_to_customer_avg": amount_ratio,
        "customer_txn_count_before": customer_txn_count_before,
        "is_new_device": is_new_device,
        "is_new_ip": is_new_ip,
        "is_new_location": is_new_location,
        "hours_since_last_txn": hours_since_last,
        "txn_count_last_1h": txn_count_last_1h,
        "txn_count_last_24h": txn_count_last_24h,
        "device_customer_count_so_far": device_customer_count,
        "account_age_days": customer.account_age_days,
        "hour_of_day": transaction.timestamp.hour,
        "day_of_week": transaction.timestamp.weekday(),
        "payment_method": transaction.payment_method,
        "merchant_category": transaction.merchant.category,
    }


def score_ml(transaction) -> tuple[float, dict]:
    """Returns (ml_score 0-100, feature_dict used) for a transaction."""
    model = _load_model()
    features = compute_live_features(transaction)
    row = {col: features[col] for col in FEATURE_COLUMNS + CATEGORICAL_COLUMNS}
    X = pd.DataFrame([row])
    proba = model.predict_proba(X)[0, 1]
    return round(float(proba) * 100, 2), features


def confidence_from_history(customer_txn_count_before: int) -> str:
    """
    A customer with almost no transaction history gives the model very
    little to compare against - the score is still produced, but flagged
    lower-confidence so investigators (and the LLM) don't over-trust it.
    """
    if customer_txn_count_before >= 5:
        return "high"
    if customer_txn_count_before >= 1:
        return "medium"
    return "low"


def categorize_risk(final_score: float) -> str:
    thresholds = settings.RISK_THRESHOLDS
    if final_score >= thresholds["high"]:
        return "high"
    if final_score >= thresholds["medium"]:
        return "medium"
    return "low"


def recommend_action(risk_category: str, confidence: str) -> str:
    """
    Bounded action vocabulary only - never an irreversible action like
    'block_account'. See ARCHITECTURE.md / LLM.md for the safety rationale.
    """
    if confidence == "low":
        return "manual_review"
    if risk_category == "high":
        return "escalate"
    if risk_category == "medium":
        return "manual_review"
    return "monitor"


def run_risk_pipeline(transaction):
    """
    Full pipeline entry point, called right after a transaction is created.

    Combines four independent sub-scores into a single final_score:
      - ml_score          (RandomForest fraud probability)
      - rule_score        (deterministic threshold rules)
      - behavioral_score  (statistical deviation from customer's own history)
      - graph_score       (relationship/cluster analysis)

    Weights below give the ML model (our most rigorously evaluated signal)
    the largest say, while still letting the other three sub-systems
    meaningfully move the score - this also means if the ML model were
    ever unavailable, rule/behavioral signals alone still produce a usable
    (if less complete) risk assessment, which is exactly the kind of
    graceful degradation a financial risk system needs.
    """
    from apps.behavior.rules import evaluate_rules
    from apps.behavior.anomaly import evaluate_behavioral
    from apps.evidence.models import Evidence
    from apps.graph.services import graph_score_and_evidence
    from apps.risk.models import RiskAssessment

    ml_score, features = score_ml(transaction)
    rule_score, rule_evidence = evaluate_rules(transaction, features)
    behavioral_score, behavioral_evidence = evaluate_behavioral(transaction, features)
    graph_score, graph_evidence = graph_score_and_evidence(transaction, features)

    final_score = round(
        ml_score * 0.40 + rule_score * 0.25 + behavioral_score * 0.20 + graph_score * 0.15, 2
    )

    risk_category = categorize_risk(final_score)
    confidence = confidence_from_history(features["customer_txn_count_before"])
    action = recommend_action(risk_category, confidence)

    assessment = RiskAssessment.objects.create(
        transaction=transaction,
        ml_score=ml_score,
        rule_score=rule_score,
        behavioral_score=behavioral_score,
        graph_score=graph_score,
        final_score=final_score,
        risk_category=risk_category,
        confidence=confidence,
        recommended_action=action,
    )

    evidence_rows = []
    for item in rule_evidence:
        evidence_rows.append(Evidence(
            risk_assessment=assessment, evidence_type="rule",
            description=item["description"], structured_payload=item,
        ))
    for item in behavioral_evidence:
        evidence_rows.append(Evidence(
            risk_assessment=assessment, evidence_type="behavioral",
            description=item["description"], structured_payload=item,
        ))
    for item in graph_evidence:
        evidence_rows.append(Evidence(
            risk_assessment=assessment, evidence_type="graph",
            description=item["description"], structured_payload=item,
        ))
    evidence_rows.append(Evidence(
        risk_assessment=assessment, evidence_type="model",
        description=f"ML model estimated a {ml_score:.1f}% fraud probability "
                     f"(RandomForest, trained on historical transaction patterns).",
        structured_payload={"ml_score": ml_score, "model_version": assessment.model_version},
    ))
    if not evidence_rows[:-1]:  # only the always-present model row exists
        evidence_rows.append(Evidence(
            risk_assessment=assessment, evidence_type="model",
            description="No rule, behavioral, or graph signals were triggered for this transaction.",
            structured_payload={},
        ))
    Evidence.objects.bulk_create(evidence_rows)

    return assessment, features
