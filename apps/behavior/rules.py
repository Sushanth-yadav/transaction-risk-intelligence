"""
Rule engine: deterministic, threshold-based fraud signals. Every rule is a
simple "if condition then flag with weight" statement - no statistics, no
model - which makes this sub-system fully explainable and available even
if the ML model or behavioral detector fails (see apps.risk.services'
graceful-failure handling).

Each triggered rule contributes a fixed weight toward rule_score (0-100,
capped). Weights are hand-set based on how strong a signal each pattern is
for the fraud types our synthetic data models (see ml/data/
generate_synthetic_data.py) - documented per-rule below.
"""

RULES = []


def rule(name, weight, description_fn):
    """Decorator registering a rule function. Each rule function takes
    (transaction, features) and returns True/False for whether it fires."""
    def wrapper(fn):
        RULES.append({"name": name, "weight": weight, "check": fn, "describe": description_fn})
        return fn
    return wrapper


@rule("large_amount_jump", 30, lambda f: f"Amount is {f['amount_ratio_to_customer_avg']:.1f}x this customer's historical average")
def _rule_large_amount(transaction, features):
    return features["amount_ratio_to_customer_avg"] > 5


@rule("extreme_amount_jump", 20, lambda f: f"Amount is {f['amount_ratio_to_customer_avg']:.1f}x historical average (extreme)")
def _rule_extreme_amount(transaction, features):
    # stacks with large_amount_jump for very extreme cases
    return features["amount_ratio_to_customer_avg"] > 10


@rule("new_device_and_location", 25, lambda f: "Transaction uses a device AND a location never seen before for this customer")
def _rule_new_device_location(transaction, features):
    return bool(features["is_new_device"]) and bool(features["is_new_location"])


@rule("high_velocity", 25, lambda f: f"{f['txn_count_last_1h']} other transactions from this customer in the last hour")
def _rule_velocity(transaction, features):
    return features["txn_count_last_1h"] >= 3


@rule("shared_device", 20, lambda f: f"This device has been used by {f['device_customer_count_so_far']} other customer(s)")
def _rule_shared_device(transaction, features):
    return features["device_customer_count_so_far"] > 0


@rule("new_account_high_value", 20, lambda f: f"Account is {f['account_age_days']} days old with an above-average transaction")
def _rule_new_account(transaction, features):
    return features["account_age_days"] < 30 and features["amount_ratio_to_customer_avg"] > 3


@rule("no_history_available", 10, lambda f: "No prior transaction history exists for this customer")
def _rule_no_history(transaction, features):
    return features["customer_txn_count_before"] == 0


def evaluate_rules(transaction, features: dict):
    """
    Returns (rule_score: float 0-100, evidence: list[dict]).
    Each evidence dict: {rule_name, description, weight}.
    """
    triggered = []
    for r in RULES:
        if r["check"](transaction, features):
            triggered.append({
                "rule_name": r["name"],
                "description": r["describe"](features),
                "weight": r["weight"],
            })

    rule_score = min(100, sum(t["weight"] for t in triggered))
    return rule_score, triggered
