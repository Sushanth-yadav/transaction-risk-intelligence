"""
RazorGuard Investigation Orchestrator

Gemini is used as an explanation layer.
RazorGuard's deterministic risk engine remains authoritative.

The assistant should answer natural questions about a transaction,
not only questions about flagged transactions.
"""

import json
import os
import re
from typing import Any, Dict, Optional

from django.conf import settings

from apps.transactions.models import Transaction

from .tools import TOOL_REGISTRY


# ============================================================
# GEMINI CONFIGURATION
# ============================================================

GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY",
    getattr(settings, "GEMINI_API_KEY", ""),
)

GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-2.5-flash",
)


# ============================================================
# BASIC HELPERS
# ============================================================

def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _risk_level(score: Optional[float]) -> str:
    if score is None:
        return "unknown"

    if score >= 70:
        return "high"

    if score >= 40:
        return "medium"

    if score < 5:
        return "trusted"

    return "low"


# ============================================================
# TRANSACTION CONTEXT
# ============================================================

def _get_transaction_context(
    transaction_id: str,
) -> Dict[str, Any]:

    txn = (
        Transaction.objects
        .select_related(
            "customer",
            "merchant",
            "device",
            "ip_address",
            "risk_assessment",
        )
        .filter(
            transaction_id=transaction_id
        )
        .first()
    )

    if not txn:
        return {
            "error": (
                f"Transaction {transaction_id} "
                "was not found."
            )
        }

    assessment = getattr(
        txn,
        "risk_assessment",
        None,
    )

    if not assessment:
        return {
            "transaction_id": txn.transaction_id,
            "amount": _safe_float(txn.amount),
            "timestamp": str(txn.timestamp),
            "customer_id": getattr(
                txn.customer,
                "customer_id",
                None,
            ),
            "risk_assessment": None,
            "message": (
                "No RazorGuard risk assessment "
                "is available."
            ),
        }

    score = _safe_float(
        assessment.final_score
    )

    return {
        "transaction_id": txn.transaction_id,

        "amount": _safe_float(
            txn.amount
        ),

        "timestamp": str(
            txn.timestamp
        ),

        "customer_id": getattr(
            txn.customer,
            "customer_id",
            None,
        ),

        "merchant": getattr(
            txn.merchant,
            "merchant_id",
            None,
        ),

        "device": getattr(
            txn.device,
            "device_id",
            None,
        ),

        "ip_address": getattr(
            txn.ip_address,
            "ip_id",
            None,
        ),

        "risk_assessment": {
            "final_score": score,

            "risk_category": (
                assessment.risk_category
            ),

            "recommended_action": getattr(
                assessment,
                "recommended_action",
                None,
            ),

            "confidence": getattr(
                assessment,
                "confidence",
                None,
            ),

            "ml_score": _safe_float(
                getattr(
                    assessment,
                    "ml_score",
                    0,
                )
            ),

            "rule_score": _safe_float(
                getattr(
                    assessment,
                    "rule_score",
                    0,
                )
            ),

            "behavioral_score": _safe_float(
                getattr(
                    assessment,
                    "behavioral_score",
                    0,
                )
            ),

            "graph_score": _safe_float(
                getattr(
                    assessment,
                    "graph_score",
                    0,
                )
            ),

            "risk_level": _risk_level(
                score
            ),
        },
    }


# ============================================================
# QUESTION INTENT
# ============================================================

def _detect_question_intent(
    question: str,
) -> str:

    q = (question or "").lower().strip()

    # --------------------------------------------------------
    # SAFE / NOT SUSPICIOUS
    # --------------------------------------------------------

    if any(
        phrase in q
        for phrase in [
            "why no suspicious",
            "why not suspicious",
            "why is it not suspicious",
            "why is this not suspicious",
            "why isn't it suspicious",
            "why isn't this suspicious",
            "why is it safe",
            "why is this safe",
            "why safe",
            "why is it not risky",
            "why isn't it risky",
            "is it safe",
            "is this safe",
            "does this look safe",
            "why normal",
        ]
    ):
        return "why_not_suspicious"

    # --------------------------------------------------------
    # SUSPICIOUS / FRAUD
    # --------------------------------------------------------

    if any(
        phrase in q
        for phrase in [
            "is this suspicious",
            "is it suspicious",
            "does this look suspicious",
            "does this seem suspicious",
            "should i be worried",
            "should we be worried",
            "is this fraud",
            "is it fraud",
            "is this fraudulent",
            "is it fraudulent",
            "fraudulent",
            "should i block",
            "should we block",
        ]
    ):
        return "suspicion_assessment"

    # --------------------------------------------------------
    # RISK FACTORS
    # --------------------------------------------------------

    if any(
        phrase in q
        for phrase in [
            "what caused the risk",
            "what caused risk",
            "what increased the risk",
            "what are the risk factors",
            "risk factors",
            "risk signals",
            "what made this risky",
            "why risky",
            "why is this risky",
            "why risk",
        ]
    ):
        return "risk_factors"

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    if any(
        phrase in q
        for phrase in [
            "explain the score",
            "explain score",
            "risk score",
            "explain risk score",
            "score explanation",
            "what is the score",
            "how was the score calculated",
        ]
    ):
        return "score_explanation"

    # --------------------------------------------------------
    # BEHAVIOR
    # --------------------------------------------------------

    if any(
        phrase in q
        for phrase in [
            "behavior",
            "behaviour",
            "customer behavior",
            "customer behaviour",
            "customer activity",
            "activity pattern",
            "normal activity",
        ]
    ):
        return "behavior"

    # --------------------------------------------------------
    # EVIDENCE
    # --------------------------------------------------------

    if any(
        phrase in q
        for phrase in [
            "evidence",
            "what evidence",
            "show evidence",
            "what supports",
            "what proves",
        ]
    ):
        return "evidence"

    # --------------------------------------------------------
    # GENERAL TRANSACTION QUESTIONS
    # --------------------------------------------------------

    if any(
        phrase in q
        for phrase in [
            "what happened",
            "explain this",
            "explain transaction",
            "tell me about this",
            "tell me about the transaction",
            "transaction details",
            "what do you know",
            "give me details",
            "analyse this",
            "analyze this",
        ]
    ):
        return "general_transaction"

    return "general"


# ============================================================
# INVESTIGATION TOOL CONTEXT
# ============================================================

def _collect_tool_context(
    transaction_id: str,
) -> Dict[str, Any]:

    try:

        tool = TOOL_REGISTRY.get(
            "get_investigation_context"
        )

        if not tool:
            return {}

        result = tool(
            transaction_id
        )

        if not isinstance(
            result,
            dict,
        ):
            return {}

        return {
            "get_investigation_context": result
        }

    except Exception:
        return {}


# ============================================================
# RISK SUMMARY
# ============================================================

def _build_risk_summary(
    context: Dict[str, Any],
) -> str:

    assessment = context.get(
        "risk_assessment"
    )

    if not isinstance(
        assessment,
        dict,
    ):
        return (
            "No RazorGuard risk assessment "
            "is available."
        )

    score = _safe_float(
        assessment.get(
            "final_score"
        )
    )

    category = assessment.get(
        "risk_category",
        "unknown",
    )

    action = assessment.get(
        "recommended_action",
        "not specified",
    )

    confidence = assessment.get(
        "confidence",
        "not specified",
    )

    ml = _safe_float(
        assessment.get(
            "ml_score"
        )
    )

    rule = _safe_float(
        assessment.get(
            "rule_score"
        )
    )

    behavioral = _safe_float(
        assessment.get(
            "behavioral_score"
        )
    )

    graph = _safe_float(
        assessment.get(
            "graph_score"
        )
    )

    lines = [
        f"Final score: {score:.2f}/100",
        f"Risk category: {category}",
        f"Risk level: {_risk_level(score)}",
        f"Recommended action: {action}",
        f"Confidence: {confidence}",
        f"ML score: {ml:.2f}",
        f"Rule score: {rule:.2f}",
        f"Behavioral score: {behavioral:.2f}",
        f"Graph score: {graph:.2f}",
    ]

    if ml < 5:
        lines.append(
            "The ML signal is low."
        )

    if rule == 0:
        lines.append(
            "There is no rule-based risk contribution."
        )

    if graph == 0:
        lines.append(
            "There is no graph-based risk contribution."
        )

    if behavioral > 0:
        lines.append(
            "Behavioral analysis contributed some risk."
        )

    if score < 5:
        lines.append(
            "The transaction is in RazorGuard's "
            "extremely low-risk/trusted range."
        )
    elif score < 40:
        lines.append(
            "The transaction is classified as low risk."
        )
    elif score < 70:
        lines.append(
            "The transaction is classified as medium risk."
        )
    else:
        lines.append(
            "The transaction is classified as high risk."
        )

    return "\n".join(lines)


# ============================================================
# DETERMINISTIC FALLBACK
# ============================================================

def _fallback_answer(
    question: str,
    context: Dict[str, Any],
) -> str:

    assessment = context.get(
        "risk_assessment"
    )

    if not isinstance(
        assessment,
        dict,
    ):
        return (
            "### Investigation result\n\n"
            "RazorGuard does not have enough risk "
            "assessment data for this transaction."
        )

    score = _safe_float(
        assessment.get(
            "final_score"
        )
    )

    category = str(
        assessment.get(
            "risk_category",
            "unknown",
        )
    ).lower()

    action = (
        assessment.get(
            "recommended_action"
        )
        or "not specified"
    )

    ml = _safe_float(
        assessment.get(
            "ml_score"
        )
    )

    rule = _safe_float(
        assessment.get(
            "rule_score"
        )
    )

    behavioral = _safe_float(
        assessment.get(
            "behavioral_score"
        )
    )

    graph = _safe_float(
        assessment.get(
            "graph_score"
        )
    )

    investigation = context.get(
        "investigation_context",
        {},
    )

    if not isinstance(
        investigation,
        dict,
    ):
        investigation = {}

    current = investigation.get(
        "current_activity",
        {},
    )

    if not isinstance(
        current,
        dict,
    ):
        current = {}

    baseline = investigation.get(
        "customer_baseline",
        {},
    )

    if not isinstance(
        baseline,
        dict,
    ):
        baseline = {}

    comparison = investigation.get(
        "behavioral_comparison",
        {},
    )

    if not isinstance(
        comparison,
        dict,
    ):
        comparison = {}

    root_causes = investigation.get(
        "root_cause_signals",
        [],
    )

    if not isinstance(
        root_causes,
        list,
    ):
        root_causes = []

    negative_signals = investigation.get(
        "negative_signals",
        [],
    )

    if not isinstance(
        negative_signals,
        list,
    ):
        negative_signals = []

    intent = _detect_question_intent(
        question
    )

    # --------------------------------------------------------
    # SIGNALS
    # --------------------------------------------------------

    risk_factors = []

    if comparison.get(
        "is_new_location",
        False,
    ):
        risk_factors.append(
            "A new transaction location was observed."
        )

    if comparison.get(
        "is_new_device",
        False,
    ):
        risk_factors.append(
            "A new device was observed."
        )

    if comparison.get(
        "is_new_ip",
        False,
    ):
        risk_factors.append(
            "A new IP address was observed."
        )

    if comparison.get(
        "amount_unusual",
        False,
    ):
        ratio = comparison.get(
            "amount_ratio_to_average"
        )

        average = baseline.get(
            "average_amount"
        )

        amount = current.get(
            "amount"
        )

        if (
            isinstance(amount, (int, float))
            and isinstance(average, (int, float))
        ):
            risk_factors.append(
                f"The transaction amount was "
                f"₹{amount:.2f}, compared with an "
                f"average of ₹{average:.2f}."
            )
        elif isinstance(
            ratio,
            (int, float),
        ):
            risk_factors.append(
                "The transaction amount differs "
                "from the customer's normal pattern."
            )

    transactions_24h = comparison.get(
        "transactions_last_24h"
    )

    if isinstance(
        transactions_24h,
        (int, float),
    ):
        if transactions_24h >= 3:
            risk_factors.append(
                f"There were {int(transactions_24h)} "
                "transactions in the last 24 hours."
            )

    if ml >= 5:
        risk_factors.append(
            f"The ML component contributed "
            f"{ml:.1f} points."
        )

    if rule > 0:
        risk_factors.append(
            f"A rule-based signal contributed "
            f"{rule:.1f} points."
        )

    if graph > 0:
        risk_factors.append(
            f"A graph-based signal contributed "
            f"{graph:.1f} points."
        )

    reassuring = []

    if ml < 5:
        reassuring.append(
            "The ML fraud signal is low."
        )

    if rule == 0:
        reassuring.append(
            "No rule-based risk signal was detected."
        )

    if graph == 0:
        reassuring.append(
            "No graph-based suspicious relationship "
            "was detected."
        )

    if not comparison.get(
        "is_new_location",
        False,
    ):
        reassuring.append(
            "The transaction location was previously "
            "seen for this customer."
        )

    if not comparison.get(
        "is_new_device",
        False,
    ):
        reassuring.append(
            "The transaction device was previously "
            "seen for this customer."
        )

    if not comparison.get(
        "is_new_ip",
        False,
    ):
        reassuring.append(
            "The transaction IP was previously "
            "seen for this customer."
        )

    if not comparison.get(
        "amount_unusual",
        False,
    ):
        reassuring.append(
            "The transaction amount was not marked "
            "as unusual."
        )

    # --------------------------------------------------------
    # WHY NOT SUSPICIOUS
    # --------------------------------------------------------

    if intent == "why_not_suspicious":

        return "\n".join(
            [
                "### Why this transaction is not strongly suspicious",
                "",
                f"RazorGuard's final score is "
                f"**{score:.1f}/100** and the transaction "
                f"is classified as **{category.upper()} risk**.",
                "",
                "### Evidence reducing concern",
                "",
                *(
                    f"- {item}"
                    for item in reassuring
                ),
                "",
                "### What contributed some risk",
                "",
                (
                    "\n".join(
                        f"- {item}"
                        for item in risk_factors
                    )
                    if risk_factors
                    else
                    "- No significant risk factor was identified."
                ),
                "",
                "### Overall assessment",
                "",
                "The available RazorGuard evidence does "
                "not indicate strong evidence of fraud.",
                "",
                f"Recommended action: **{action}**.",
            ]
        )

    # --------------------------------------------------------
    # SUSPICION ASSESSMENT
    # --------------------------------------------------------

    if intent == "suspicion_assessment":

        if score >= 70:
            conclusion = (
                "Yes, this transaction should be treated "
                "as high risk and investigated."
            )
        elif score >= 40:
            conclusion = (
                "There are meaningful risk signals, so "
                "additional review is appropriate."
            )
        else:
            conclusion = (
                "The available RazorGuard evidence does "
                "not indicate strong evidence of fraud."
            )

        return "\n".join(
            [
                "### Suspicion assessment",
                "",
                f"RazorGuard score: **{score:.1f}/100**",
                f"Risk category: **{category.upper()}**",
                "",
                conclusion,
                "",
                "### Main signals",
                "",
                (
                    "\n".join(
                        f"- {item}"
                        for item in risk_factors
                    )
                    if risk_factors
                    else
                    "- No strong suspicious signal was identified."
                ),
                "",
                "### Evidence reducing concern",
                "",
                (
                    "\n".join(
                        f"- {item}"
                        for item in reassuring
                    )
                    if reassuring
                    else
                    "- No additional reassuring signal was identified."
                ),
                "",
                f"Recommended action: **{action}**.",
            ]
        )

    # --------------------------------------------------------
    # RISK FACTORS
    # --------------------------------------------------------

    if intent == "risk_factors":

        return "\n".join(
            [
                "### What caused the risk",
                "",
                f"RazorGuard calculated a score of "
                f"**{score:.1f}/100**.",
                "",
                (
                    "\n".join(
                        f"- {item}"
                        for item in risk_factors
                    )
                    if risk_factors
                    else
                    "- No strong individual risk factor was identified."
                ),
                "",
                "A behavioral difference or model signal "
                "does not automatically mean fraud.",
            ]
        )

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    if intent == "score_explanation":

        return "\n".join(
            [
                "### Risk score explanation",
                "",
                f"Final score: **{score:.1f}/100**",
                f"Category: **{category.upper()}**",
                "",
                f"- ML: **{ml:.1f}**",
                f"- Rules: **{rule:.1f}**",
                f"- Behavioral: **{behavioral:.1f}**",
                f"- Graph: **{graph:.1f}**",
                "",
                f"Recommended action: **{action}**.",
            ]
        )

    # --------------------------------------------------------
    # GENERAL / DEFAULT
    # --------------------------------------------------------

    return "\n".join(
        [
            "### RazorGuard transaction assessment",
            "",
            f"Transaction: `{context.get('transaction_id')}`",
            "",
            f"Risk score: **{score:.1f}/100**",
            f"Risk category: **{category.upper()}**",
            f"Recommended action: **{action}**",
            "",
            "### Main risk signals",
            "",
            (
                "\n".join(
                    f"- {item}"
                    for item in risk_factors
                )
                if risk_factors
                else
                "- No strong risk signal was identified."
            ),
            "",
            "### Signals reducing concern",
            "",
            (
                "\n".join(
                    f"- {item}"
                    for item in reassuring
                )
                if reassuring
                else
                "- No additional reassuring signal was identified."
            ),
            "",
            "RazorGuard's risk engine is authoritative. "
            "The assistant explains the available evidence "
            "but does not change the underlying risk decision.",
        ]
    )


# ============================================================
# GEMINI CLIENT
# ============================================================

def _get_gemini_client():

    if not GEMINI_API_KEY:
        return None

    try:

        from google import genai

        return genai.Client(
            api_key=GEMINI_API_KEY
        )

    except Exception:
        return None


# ============================================================
# GEMINI PROMPT
# ============================================================

def _system_prompt(
    context: Dict[str, Any],
    intent: str,
) -> str:

    risk_summary = _build_risk_summary(
        context
    )

    investigation_context = context.get(
        "investigation_context",
        {},
    )

    return f"""
You are the RazorGuard Investigation Assistant.

You answer natural questions about payment transactions.

The user may ask anything such as:

- is this suspicious
- why no suspicious
- is this safe
- what happened
- explain this transaction
- what caused the risk
- why is the score high
- what evidence do we have
- should I be worried
- tell me about this transaction

Do NOT assume the transaction was flagged.

The RazorGuard risk engine is authoritative.

============================================================
STRICT RULES
============================================================

1. Never invent evidence.

2. Never invent a device, IP, location, merchant,
   customer behavior, graph relationship, or fraud signal.

3. Only use information contained in the supplied data.

4. Never change the final RazorGuard score.

5. Never change the RazorGuard risk category.

6. Never claim confirmed fraud unless the supplied
   data explicitly confirms fraud.

7. Unusual does not automatically mean fraudulent.

8. A low ML score means the model signal is low.

9. A zero rule score means no rule contribution.

10. A zero graph score means no graph contribution.

11. If the transaction is trusted or low risk,
    clearly say so.

12. If the user asks "is this suspicious", answer
    whether the available RazorGuard evidence indicates
    meaningful suspicion.

13. If the user asks "why no suspicious", explain why
    the evidence does NOT strongly indicate suspicion.

14. Do not rewrite every question as
    "why was this transaction flagged?"

15. If a factor is absent, do not invent it.

16. Explain specific evidence before generic explanations.

17. Distinguish:
    - risk-increasing evidence
    - reassuring evidence
    - final decision

18. The recommended action is not proof of fraud.

19. Keep the answer concise and understandable.

============================================================
USER INTENT
============================================================

{intent}

============================================================
AUTHORITATIVE RISK SUMMARY
============================================================

{risk_summary}

============================================================
INVESTIGATION CONTEXT
============================================================

{json.dumps(
    investigation_context,
    indent=2,
    default=str,
)}

============================================================
FULL AUTHORITATIVE CONTEXT
============================================================

{json.dumps(
    context,
    indent=2,
    default=str,
)}

Answer the user's question directly.
"""


# ============================================================
# GEMINI ANSWER
# ============================================================

def _ask_gemini(
    question: str,
    context: Dict[str, Any],
) -> Optional[str]:

    client = _get_gemini_client()

    if not client:
        return None

    intent = _detect_question_intent(
        question
    )

    prompt = (
        _system_prompt(
            context,
            intent,
        )
        + "\n\nUSER QUESTION:\n"
        + question
    )

    try:

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )

        text = getattr(
            response,
            "text",
            None,
        )

        if text:
            return text.strip()

    except Exception:
        return None

    return None


# ============================================================
# GEMINI VALIDATION
# ============================================================

def _validate_answer(
    answer: str,
    context: Dict[str, Any],
) -> str:

    assessment = context.get(
        "risk_assessment"
    )

    if not isinstance(
        assessment,
        dict,
    ):
        return answer

    score = _safe_float(
        assessment.get(
            "final_score"
        )
    )

    category = str(
        assessment.get(
            "risk_category",
            "",
        )
    ).lower()

    ml = _safe_float(
        assessment.get(
            "ml_score"
        )
    )

    lower = answer.lower()

    # --------------------------------------------------------
    # Very low risk protection
    # --------------------------------------------------------

    if score < 5:

        dangerous = [
            "confirmed fraud",
            "definitely fraud",
            "definitely fraudulent",
            "strong fraud signal",
            "highly suspicious",
            "high risk",
        ]

        if any(
            phrase in lower
            for phrase in dangerous
        ):
            return _fallback_answer(
                "why no suspicious",
                context,
            )

    # --------------------------------------------------------
    # Low ML protection
    # --------------------------------------------------------

    if ml < 5:

        dangerous_ml = [
            "strong ml warning",
            "strong model warning",
            "model detected strong fraud",
            "strong fraud probability",
        ]

        if any(
            phrase in lower
            for phrase in dangerous_ml
        ):
            return _fallback_answer(
                "what caused the risk",
                context,
            )

    # --------------------------------------------------------
    # Low category protection
    # --------------------------------------------------------

    if category == "low" and score < 40:

        if (
            "high risk" in lower
            or "high-risk" in lower
        ):
            return _fallback_answer(
                "is this suspicious",
                context,
            )

    return answer


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

def ask_investigation_assistant(
    question: str,
    default_transaction_id: Optional[str] = None,
) -> Dict[str, Any]:

    question = (
        question or ""
    ).strip()

    if not question:

        return {
            "answer": (
                "Ask me anything about this transaction "
                "or its risk assessment."
            ),
            "tools_called": [],
        }

    # --------------------------------------------------------
    # Determine transaction ID
    # --------------------------------------------------------

    transaction_id = (
        default_transaction_id
    )

    if not transaction_id:

        match = re.search(
            r"(txn_[a-zA-Z0-9_-]+)",
            question,
        )

        if match:
            transaction_id = (
                match.group(1)
            )

    if not transaction_id:

        return {
            "answer": (
                "I need a transaction ID to investigate "
                "a specific transaction."
            ),
            "tools_called": [],
        }

    # --------------------------------------------------------
    # Load authoritative context
    # --------------------------------------------------------

    context = _get_transaction_context(
        transaction_id
    )

    if context.get("error"):

        return {
            "transaction_id": transaction_id,
            "question": question,
            "answer": context["error"],
            "tools_called": [],
        }

    # --------------------------------------------------------
    # Collect investigation context
    # --------------------------------------------------------

    tool_context = _collect_tool_context(
        transaction_id
    )

    investigation_context = (
        tool_context.get(
            "get_investigation_context",
            {},
        )
        if isinstance(
            tool_context,
            dict,
        )
        else {}
    )

    if isinstance(
        investigation_context,
        dict,
    ):
        context[
            "investigation_context"
        ] = investigation_context

    # --------------------------------------------------------
    # Ask Gemini
    # --------------------------------------------------------

    answer = _ask_gemini(
        question,
        context,
    )

    # --------------------------------------------------------
    # Deterministic fallback
    # --------------------------------------------------------

    if not answer:

        answer = _fallback_answer(
            question,
            context,
        )

    # --------------------------------------------------------
    # Validate answer
    # --------------------------------------------------------

    answer = _validate_answer(
        answer,
        context,
    )

    # --------------------------------------------------------
    # Return API response
    # --------------------------------------------------------

    return {
        "transaction_id": transaction_id,
        "question": question,
        "answer": answer,
        "tools_called": list(
            tool_context.keys()
        )
        if isinstance(
            tool_context,
            dict,
        )
        else [],
    }