"""
Behavioral anomaly detector: unlike the rule engine (fixed thresholds),
this measures how unusual a transaction is relative to THIS customer's own
historical distribution - amount z-score, how rare this hour-of-day is for
them, and whether today's transaction velocity is far above their normal
daily rate. This catches subtler deviations a flat threshold would miss
(e.g. a customer who normally spends ₹200 suddenly spending ₹2,000 is
mild by a fixed-threshold rule, but a large z-score against THEIR history).

Components are only counted when there is enough history to judge them
fairly - with too little history we stay neutral rather than penalizing a
customer for information we don't have (this also feeds the "confidence"
signal used elsewhere in the pipeline).
"""

from datetime import timedelta

MIN_HISTORY_FOR_HOUR_RARITY = 5


def _hour_rarity_score(transaction, prior_timestamps) -> tuple[float, str | None]:
    """
    What fraction of this customer's past transactions happened within a
    +/-2 hour window of the current transaction's hour? A low fraction
    (with enough history to judge) means this is an unusual time for them.
    """
    if len(prior_timestamps) < MIN_HISTORY_FOR_HOUR_RARITY:
        return 0.0, None

    current_hour = transaction.timestamp.hour
    close_hours = {(current_hour + delta) % 24 for delta in range(-2, 3)}
    matches = sum(1 for ts in prior_timestamps if ts.hour in close_hours)
    proportion = matches / len(prior_timestamps)

    score = max(0.0, (1 - proportion)) * 100
    if proportion < 0.15:
        desc = (f"Transaction occurs at an hour highly unusual for this customer "
                f"(only {proportion:.0%} of their past transactions happen near this time)")
        return score, desc
    return score, None


def _velocity_anomaly_score(features: dict) -> tuple[float, str | None]:
    account_age = max(features["account_age_days"], 1)
    typical_daily_rate = features["customer_txn_count_before"] / account_age
    actual_24h = features["txn_count_last_24h"]

    if typical_daily_rate < 0.05:
        # customer transacts too rarely for a "typical daily rate" to be meaningful
        if actual_24h >= 2:
            return 60.0, f"{actual_24h} transactions in 24h for a customer who rarely transacts"
        return 0.0, None

    ratio = actual_24h / typical_daily_rate
    score = min(100.0, max(0.0, (ratio - 1)) * 30)
    if ratio > 3:
        return score, f"Transaction frequency is {ratio:.1f}x this customer's typical daily rate"
    return score, None


def _amount_anomaly_score(features: dict) -> tuple[float, str | None]:
    z = features["amount_zscore_vs_customer"]
    score = min(100.0, abs(z) * 8)
    if abs(z) > 2:
        return score, f"Amount is {z:.1f} standard deviations from this customer's typical amount"
    return score, None


def _novelty_score(features: dict) -> tuple[float, str | None]:
    flags = [features["is_new_device"], features["is_new_ip"], features["is_new_location"]]
    score = (sum(flags) / len(flags)) * 100
    if sum(flags) >= 2:
        which = []
        if features["is_new_device"]:
            which.append("device")
        if features["is_new_ip"]:
            which.append("IP")
        if features["is_new_location"]:
            which.append("location")
        return score, f"Multiple new identifiers for this customer at once: {', '.join(which)}"
    return score, None


def evaluate_behavioral(transaction, features: dict):
    """
    Returns (behavioral_score: float 0-100, evidence: list[dict]).
    """
    customer = transaction.customer
    prior_timestamps = list(
        customer.transactions
        .filter(timestamp__lt=transaction.timestamp)
        .order_by("timestamp")
        .values_list("timestamp", flat=True)
    )

    amount_score, amount_desc = _amount_anomaly_score(features)
    hour_score, hour_desc = _hour_rarity_score(transaction, prior_timestamps)
    velocity_score, velocity_desc = _velocity_anomaly_score(features)
    novelty_score, novelty_desc = _novelty_score(features)

    behavioral_score = (
        amount_score * 0.40 + hour_score * 0.20 + velocity_score * 0.20 + novelty_score * 0.20
    )

    evidence = []
    for score_name, desc in [
        ("amount_anomaly", amount_desc),
        ("time_anomaly", hour_desc),
        ("frequency_anomaly", velocity_desc),
        ("identifier_novelty", novelty_desc),
    ]:
        if desc:
            evidence.append({"signal": score_name, "description": desc})

    return round(min(100.0, behavioral_score), 2), evidence
