"""
RazorGuard Investigation Assistant Tools

The LLM never accesses Django ORM/database directly.

Every investigation fact is collected by backend-controlled tools and
returned as bounded JSON-serializable data. Gemini is responsible only for
interpreting these verified facts and explaining them to the investigator.

IMPORTANT:
- Never invent transaction facts.
- Never invent IP/device/location anomalies.
- Never change the risk decision.
- The RiskAssessment remains the authoritative risk decision.
- The assistant explains why the risk engine produced its result.
"""

from datetime import timedelta

from django.utils import timezone

from apps.audit.models import AuditLog
from apps.evidence.models import Evidence
from apps.graph.services import analyze_relationships
from apps.risk.models import RiskAssessment
from apps.transactions.models import Transaction


# =========================================================
# BASIC TRANSACTION
# =========================================================

def get_transaction(transaction_id: str) -> dict:
    """Return verified transaction details."""

    try:
        txn = (
            Transaction.objects
            .select_related(
                "customer",
                "merchant",
                "device",
                "ip_address",
            )
            .get(transaction_id=transaction_id)
        )
    except Transaction.DoesNotExist:
        return {
            "error": f"No transaction found with id {transaction_id}"
        }

    return {
        "transaction_id": txn.transaction_id,
        "customer_id": txn.customer.customer_id,
        "merchant_id": txn.merchant.merchant_id,
        "merchant_category": txn.merchant.category,
        "device_id": txn.device.device_id,
        "ip_id": txn.ip_address.ip_id,
        "amount": float(txn.amount),
        "timestamp": txn.timestamp.isoformat(),
        "location": txn.location,
        "payment_method": txn.payment_method,
    }


# =========================================================
# CUSTOMER HISTORY
# =========================================================

def get_customer_history(customer_id: str) -> dict:
    """
    Return a bounded summary of the customer's historical behaviour.

    This gives Gemini the customer's baseline so that it can explain
    whether the current transaction is actually unusual.
    """

    txns = list(
        Transaction.objects
        .filter(customer__customer_id=customer_id)
        .select_related(
            "customer",
            "device",
            "ip_address",
        )
        .order_by("timestamp")
    )

    if not txns:
        return {
            "error": f"No customer found with id {customer_id}"
        }

    customer = txns[0].customer

    amounts = [
        float(t.amount)
        for t in txns
    ]

    devices = sorted({
        t.device.device_id
        for t in txns
    })

    locations = sorted({
        t.location
        for t in txns
        if t.location
    })

    ips = sorted({
        t.ip_address.ip_id
        for t in txns
        if t.ip_address
    })

    return {
        "customer_id": customer_id,
        "account_age_days": customer.account_age_days,

        "total_transactions": len(txns),

        "average_amount": round(
            sum(amounts) / len(amounts),
            2,
        ),

        "min_amount": round(
            min(amounts),
            2,
        ),

        "max_amount": round(
            max(amounts),
            2,
        ),

        "distinct_devices_used": devices,
        "distinct_locations_used": locations,
        "distinct_ips_used": ips,

        "usual_location": (
            locations[-1]
            if locations
            else None
        ),
    }


# =========================================================
# INVESTIGATION CONTEXT / ROOT CAUSE ANALYSIS
# =========================================================

def get_investigation_context(transaction_id: str) -> dict:
    """
    Build the verified context required for a human-readable investigation.

    This is deliberately backend-derived.

    Gemini does NOT decide that an IP/device/location is new.
    The backend calculates that fact and Gemini explains it.
    """

    try:
        txn = (
            Transaction.objects
            .select_related(
                "customer",
                "merchant",
                "device",
                "ip_address",
                "risk_assessment",
            )
            .get(transaction_id=transaction_id)
        )
    except Transaction.DoesNotExist:
        return {
            "error": f"No transaction found with id {transaction_id}"
        }

    customer_id = txn.customer.customer_id

    # -----------------------------------------------------
    # Customer history before the current transaction
    # -----------------------------------------------------

    previous_txns = list(
        Transaction.objects
        .filter(
            customer__customer_id=customer_id,
            timestamp__lt=txn.timestamp,
        )
        .select_related(
            "device",
            "ip_address",
        )
        .order_by("-timestamp")
    )

    previous_amounts = [
        float(t.amount)
        for t in previous_txns
    ]

    previous_locations = sorted({
        t.location
        for t in previous_txns
        if t.location
    })

    previous_devices = sorted({
        t.device.device_id
        for t in previous_txns
        if t.device
    })

    previous_ips = sorted({
        t.ip_address.ip_id
        for t in previous_txns
        if t.ip_address
    })

    # -----------------------------------------------------
    # Current transaction values
    # -----------------------------------------------------

    current_location = txn.location

    current_device = (
        txn.device.device_id
        if txn.device
        else None
    )

    current_ip = (
        txn.ip_address.ip_id
        if txn.ip_address
        else None
    )

    current_amount = float(txn.amount)

    # -----------------------------------------------------
    # New location / device / IP
    # -----------------------------------------------------

    is_new_location = bool(
        current_location
        and current_location not in previous_locations
        and previous_txns
    )

    is_new_device = bool(
        current_device
        and current_device not in previous_devices
        and previous_txns
    )

    is_new_ip = bool(
        current_ip
        and current_ip not in previous_ips
        and previous_txns
    )

    # -----------------------------------------------------
    # Recent transaction frequency
    # -----------------------------------------------------

    window_start = txn.timestamp - timedelta(hours=24)

    transactions_last_24h = Transaction.objects.filter(
        customer__customer_id=customer_id,
        timestamp__gte=window_start,
        timestamp__lte=txn.timestamp,
    ).count()

    # -----------------------------------------------------
    # Amount deviation
    # -----------------------------------------------------

    average_amount = (
        sum(previous_amounts) / len(previous_amounts)
        if previous_amounts
        else None
    )

    amount_ratio = None
    amount_unusual = False

    if average_amount and average_amount > 0:
        amount_ratio = round(
            current_amount / average_amount,
            2,
        )

        # Conservative backend signal.
        # This does NOT mean fraud; it only means amount differs
        # materially from the customer's historical average.
        amount_unusual = (
            current_amount >= average_amount * 2
            or current_amount <= average_amount * 0.5
        )

    # -----------------------------------------------------
    # Risk assessment
    # -----------------------------------------------------

    try:
        assessment = RiskAssessment.objects.get(
            transaction=txn
        )
    except RiskAssessment.DoesNotExist:
        assessment = None

    # -----------------------------------------------------
    # Evidence
    # -----------------------------------------------------

    evidence = []

    if assessment:
        evidence_items = Evidence.objects.filter(
            risk_assessment=assessment
        )

        evidence = [
            {
                "type": item.evidence_type,
                "description": item.description,
            }
            for item in evidence_items
        ]

    # -----------------------------------------------------
    # Root-cause signals
    # -----------------------------------------------------

    root_cause_signals = []

    if is_new_location:
        root_cause_signals.append({
            "factor": "new_location",
            "severity": "attention",
            "description": (
                f"The transaction occurred in {current_location}, "
                "which was not present in the customer's previous "
                "transaction history."
            ),
        })

    if is_new_device:
        root_cause_signals.append({
            "factor": "new_device",
            "severity": "attention",
            "description": (
                "The transaction used a device that was not "
                "previously associated with this customer."
            ),
        })

    if is_new_ip:
        root_cause_signals.append({
            "factor": "new_ip",
            "severity": "attention",
            "description": (
                "The transaction originated from an IP address "
                "not previously associated with this customer."
            ),
        })

    if amount_unusual:
        root_cause_signals.append({
            "factor": "unusual_amount",
            "severity": "attention",
            "description": (
                f"The transaction amount of ₹{current_amount:.2f} "
                f"differs materially from the customer's historical "
                f"average of ₹{average_amount:.2f}."
            ),
        })

    if transactions_last_24h > 1:
        root_cause_signals.append({
            "factor": "transaction_frequency",
            "severity": "attention",
            "description": (
                f"The customer has {transactions_last_24h} "
                "transactions within the last 24 hours."
            ),
        })

    # -----------------------------------------------------
    # Explicit negative signals
    #
    # These are extremely important because the assistant must
    # be able to explain why a transaction is NOT suspicious.
    # -----------------------------------------------------

    negative_signals = []

    if assessment:

        if float(assessment.rule_score or 0) == 0:
            negative_signals.append(
                "No fraud-rule signal was generated."
            )

        if float(assessment.graph_score or 0) == 0:
            negative_signals.append(
                "No graph-risk score was generated."
            )

        if float(assessment.ml_score or 0) < 5:
            negative_signals.append(
                "The ML fraud signal is very low."
            )

    if not is_new_location and previous_txns:
        negative_signals.append(
            "The transaction location has been seen before."
        )

    if not is_new_device and previous_txns:
        negative_signals.append(
            "The transaction device has been seen before."
        )

    if not is_new_ip and previous_txns:
        negative_signals.append(
            "The transaction IP has been seen before."
        )

    # -----------------------------------------------------
    # Related entities
    # -----------------------------------------------------

    try:
        relationship_result = analyze_relationships(
            customer_id,
            current_device,
            current_ip,
        )
    except Exception:
        relationship_result = {}

    suspicious_cluster = relationship_result.get(
        "is_suspicious_cluster",
        False,
    )

    if suspicious_cluster:
        root_cause_signals.append({
            "factor": "suspicious_network",
            "severity": "high",
            "description": (
                "The transaction is connected to a suspicious "
                "entity cluster identified by the relationship analysis."
            ),
        })

    # -----------------------------------------------------
    # Final result
    # -----------------------------------------------------

    result = {
        "transaction_id": transaction_id,
        "customer_id": customer_id,

        "current_activity": {
            "amount": current_amount,
            "location": current_location,
            "device_id": current_device,
            "ip_id": current_ip,
            "payment_method": txn.payment_method,
            "timestamp": txn.timestamp.isoformat(),
        },

        "customer_baseline": {
            "previous_transaction_count": len(previous_txns),

            "average_amount": (
                round(average_amount, 2)
                if average_amount is not None
                else None
            ),

            "previous_locations": previous_locations,
            "previous_devices": previous_devices,
            "previous_ips": previous_ips,
        },

        "behavioral_comparison": {
            "is_new_location": is_new_location,
            "is_new_device": is_new_device,
            "is_new_ip": is_new_ip,

            "transactions_last_24h": transactions_last_24h,

            "amount_ratio_to_average": amount_ratio,
            "amount_unusual": amount_unusual,
        },

        "root_cause_signals": root_cause_signals,

        "negative_signals": negative_signals,

        "risk_assessment": (
            {
                "final_score": assessment.final_score,
                "risk_category": assessment.risk_category,
                "confidence": assessment.confidence,
                "recommended_action": assessment.recommended_action,

                "ml_score": assessment.ml_score,
                "rule_score": assessment.rule_score,
                "behavioral_score": assessment.behavioral_score,
                "graph_score": assessment.graph_score,

                "model_version": assessment.model_version,
            }
            if assessment
            else None
        ),

        "evidence": evidence,

        "relationships": {
            "connected_customers": relationship_result.get(
                "connected_customers",
                [],
            ),
            "connected_transactions": relationship_result.get(
                "connected_transactions",
                [],
            ),
            "connected_devices": relationship_result.get(
                "connected_devices",
                [],
            ),
            "connected_ips": relationship_result.get(
                "connected_ips",
                [],
            ),
            "component_size": relationship_result.get(
                "component_size",
                1,
            ),
            "is_suspicious_cluster": suspicious_cluster,
        },
    }

    return result


# =========================================================
# RISK EVIDENCE
# =========================================================

def get_risk_evidence(transaction_id: str) -> dict:
    """Return the authoritative risk assessment and evidence."""

    try:
        assessment = RiskAssessment.objects.get(
            transaction__transaction_id=transaction_id
        )
    except RiskAssessment.DoesNotExist:
        return {
            "error": (
                f"No risk assessment found for transaction "
                f"{transaction_id}"
            )
        }

    items = Evidence.objects.filter(
        risk_assessment=assessment
    )

    return {
        "transaction_id": transaction_id,

        "final_score": assessment.final_score,

        "risk_category": assessment.risk_category,

        "confidence": assessment.confidence,

        "recommended_action": assessment.recommended_action,

        "sub_scores": {
            "ml_score": assessment.ml_score,
            "rule_score": assessment.rule_score,
            "behavioral_score": assessment.behavioral_score,
            "graph_score": assessment.graph_score,
        },

        "evidence": [
            {
                "type": item.evidence_type,
                "description": item.description,
            }
            for item in items
        ],
    }


# =========================================================
# RELATED ENTITIES
# =========================================================

def get_related_entities(transaction_id: str) -> dict:
    """
    Return actual entities connected to the transaction through
    customer/device/IP relationships.
    """

    try:
        txn = (
            Transaction.objects
            .select_related(
                "customer",
                "device",
                "ip_address",
            )
            .get(transaction_id=transaction_id)
        )
    except Transaction.DoesNotExist:
        return {
            "error": f"No transaction found with id {transaction_id}"
        }

    result = analyze_relationships(
        txn.customer.customer_id,
        txn.device.device_id,
        txn.ip_address.ip_id,
    )

    return {
        "transaction_id": transaction_id,

        "customer_id": txn.customer.customer_id,

        "connected_customers": result.get(
            "connected_customers",
            [],
        ),

        "connected_transactions": result.get(
            "connected_transactions",
            [],
        ),

        "connected_devices": result.get(
            "connected_devices",
            [],
        ),

        "connected_ips": result.get(
            "connected_ips",
            [],
        ),

        "component_size": result.get(
            "component_size",
            1,
        ),

        "is_suspicious_cluster": result.get(
            "is_suspicious_cluster",
            False,
        ),
    }


# =========================================================
# MODEL EXPLANATION
# =========================================================

def get_model_explanation(transaction_id: str) -> dict:
    """Return verified ML score and model-related evidence."""

    try:
        assessment = RiskAssessment.objects.get(
            transaction__transaction_id=transaction_id
        )
    except RiskAssessment.DoesNotExist:
        return {
            "error": (
                f"No risk assessment found for transaction "
                f"{transaction_id}"
            )
        }

    model_evidence = Evidence.objects.filter(
        risk_assessment=assessment,
        evidence_type="model",
    )

    confidence_meanings = {
        "high": (
            "Customer has substantial prior transaction history "
            "(5+ transactions) to compare against."
        ),

        "medium": (
            "Customer has limited prior history "
            "(1-4 transactions)."
        ),

        "low": (
            "Customer has no prior transaction history. "
            "The score is therefore less reliable."
        ),
    }

    return {
        "transaction_id": transaction_id,

        "model_version": assessment.model_version,

        "ml_score": assessment.ml_score,

        "confidence": assessment.confidence,

        "confidence_meaning": confidence_meanings.get(
            assessment.confidence,
            "Confidence meaning is unavailable.",
        ),

        "notes": [
            item.description
            for item in model_evidence
        ],
    }


# =========================================================
# AUDIT HISTORY
# =========================================================

def get_audit_history(transaction_id: str) -> dict:
    """Return the verified audit history for the transaction."""

    try:
        txn = Transaction.objects.get(
            transaction_id=transaction_id
        )
    except Transaction.DoesNotExist:
        return {
            "error": f"No transaction found with id {transaction_id}"
        }

    logs = (
        AuditLog.objects
        .filter(transaction=txn)
        .order_by("timestamp")
    )

    return {
        "transaction_id": transaction_id,

        "events": [
            {
                "actor": log.actor,

                "action": log.action,

                "timestamp": log.timestamp.isoformat(),

                "question": (
                    log.new_state.get("question")
                    if isinstance(log.new_state, dict)
                    else None
                ),
            }
            for log in logs
        ],
    }


# =========================================================
# TOOL REGISTRY
# =========================================================

TOOL_REGISTRY = {
    "get_transaction": get_transaction,

    "get_customer_history": get_customer_history,

    "get_investigation_context": get_investigation_context,

    "get_risk_evidence": get_risk_evidence,

    "get_related_entities": get_related_entities,

    "get_model_explanation": get_model_explanation,

    "get_audit_history": get_audit_history,
}


# =========================================================
# TOOL SCHEMAS
# =========================================================

TOOL_SCHEMAS = [

    {
        "name": "get_transaction",

        "description": (
            "Get verified raw details of a specific transaction "
            "by transaction_id."
        ),

        "input_schema": {
            "type": "object",

            "properties": {
                "transaction_id": {
                    "type": "string"
                }
            },

            "required": [
                "transaction_id"
            ],
        },
    },

    {
        "name": "get_customer_history",

        "description": (
            "Get a verified summary of the customer's historical "
            "transaction behaviour including amount range, devices, "
            "locations, IP addresses and account age."
        ),

        "input_schema": {
            "type": "object",

            "properties": {
                "customer_id": {
                    "type": "string"
                }
            },

            "required": [
                "customer_id"
            ],
        },
    },

    {
        "name": "get_investigation_context",

        "description": (
            "Get the complete verified investigation context for a "
            "transaction. This compares the current transaction with "
            "the customer's previous behaviour and identifies whether "
            "the location, device or IP is new, whether transaction "
            "frequency is unusual, whether the amount differs materially "
            "from the customer's historical average, the authoritative "
            "risk scores, evidence, and suspicious relationship signals. "
            "Use this tool when explaining WHY a transaction received "
            "its risk category."
        ),

        "input_schema": {
            "type": "object",

            "properties": {
                "transaction_id": {
                    "type": "string"
                }
            },

            "required": [
                "transaction_id"
            ],
        },
    },

    {
        "name": "get_risk_evidence",

        "description": (
            "Get the authoritative RazorGuard risk assessment including "
            "final score, risk category, confidence, recommendation, "
            "ML, rule, behavioural and graph scores, plus evidence."
        ),

        "input_schema": {
            "type": "object",

            "properties": {
                "transaction_id": {
                    "type": "string"
                }
            },

            "required": [
                "transaction_id"
            ],
        },
    },

    {
        "name": "get_related_entities",

        "description": (
            "Get verified transactions, customers, devices and IP "
            "addresses connected through RazorGuard's relationship "
            "analysis."
        ),

        "input_schema": {
            "type": "object",

            "properties": {
                "transaction_id": {
                    "type": "string"
                }
            },

            "required": [
                "transaction_id"
            ],
        },
    },

    {
        "name": "get_model_explanation",

        "description": (
            "Get the verified ML model score, confidence and model "
            "evidence for a transaction."
        ),

        "input_schema": {
            "type": "object",

            "properties": {
                "transaction_id": {
                    "type": "string"
                }
            },

            "required": [
                "transaction_id"
            ],
        },
    },

    {
        "name": "get_audit_history",

        "description": (
            "Get the verified audit trail of investigator and system "
            "actions associated with a transaction."
        ),

        "input_schema": {
            "type": "object",

            "properties": {
                "transaction_id": {
                    "type": "string"
                }
            },

            "required": [
                "transaction_id"
            ],
        },
    },
]