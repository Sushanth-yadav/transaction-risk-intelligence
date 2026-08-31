"""
Transaction API views.

POST /api/transactions/           -> ingest a transaction, run the risk
                                      pipeline synchronously, return the
                                      transaction + risk assessment.
GET  /api/transactions/{id}/      -> transaction detail
GET  /api/transactions/{id}/risk/ -> risk assessment only
GET  /api/transactions/           -> list, filterable by risk_category

Synchronous scoring is a deliberate MVP choice: a single RandomForest
inference plus a handful of DB queries is fast (milliseconds), so there is
no need for an async task queue at this scale. If throughput ever became a
concern this would move to a background worker - noted in LIMITATIONS.md /
future work rather than built prematurely (Rule 5: simple reliable systems
over unnecessary complexity).
"""

from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import log_audit_event
from apps.risk.services import run_risk_pipeline

from .models import Customer, Device, IPAddress, Merchant, PaymentInstrument, Transaction
from .serializers import RiskAssessmentSerializer, TransactionCreateSerializer, TransactionSerializer


class TransactionListCreateView(APIView):
    def get(self, request):
        qs = Transaction.objects.select_related("customer", "merchant", "device", "ip_address")
        risk_category = request.query_params.get("risk_category")
        if risk_category:
            qs = qs.filter(risk_assessment__risk_category=risk_category)
        qs = qs[:200]
        return Response(TransactionSerializer(qs, many=True).data)

    def post(self, request):
        serializer = TransactionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with db_transaction.atomic():
            customer, _ = Customer.objects.get_or_create(
                customer_id=data["customer_id"],
                defaults={
                    "account_age_days": data["account_age_days"],
                    "avg_amount": data["customer_avg_amount"],
                },
            )
            merchant, _ = Merchant.objects.get_or_create(
                merchant_id=data["merchant_id"],
                defaults={"category": data["merchant_category"]},
            )
            device, _ = Device.objects.get_or_create(device_id=data["device_id"])
            ip_address, _ = IPAddress.objects.get_or_create(ip_id=data["ip_id"])
            instrument, _ = PaymentInstrument.objects.get_or_create(
                instrument_id=data["payment_instrument_id"]
            )

            txn = Transaction.objects.create(
                transaction_id=data["transaction_id"],
                customer=customer,
                merchant=merchant,
                device=device,
                ip_address=ip_address,
                payment_instrument=instrument,
                amount=data["amount"],
                timestamp=data["timestamp"],
                location=data["location"],
                payment_method=data["payment_method"],
            )

        try:
            assessment, _features = run_risk_pipeline(txn)
        except FileNotFoundError as exc:
            # graceful failure: transaction is still recorded, but scoring
            # is unavailable - never silently pretend a score exists
            log_audit_event(txn, actor="system", action="scoring_failed", new_state={"error": str(exc)})
            return Response(
                {
                    "transaction": TransactionSerializer(txn).data,
                    "risk_assessment": None,
                    "warning": "Risk model unavailable - transaction recorded but not scored. "
                               "Manual review required.",
                },
                status=status.HTTP_201_CREATED,
            )

        log_audit_event(
            txn, actor="system", action="risk_scored",
            new_state={"final_score": assessment.final_score, "risk_category": assessment.risk_category},
        )

        return Response(
            {
                "transaction": TransactionSerializer(txn).data,
                "risk_assessment": RiskAssessmentSerializer(_assessment_to_dict(assessment)).data,
            },
            status=status.HTTP_201_CREATED,
        )


class TransactionDetailView(APIView):
    def get(self, request, transaction_id):
        txn = get_object_or_404(Transaction, transaction_id=transaction_id)
        return Response(TransactionSerializer(txn).data)


class TransactionRiskView(APIView):
    def get(self, request, transaction_id):
        txn = get_object_or_404(Transaction, transaction_id=transaction_id)
        assessment = getattr(txn, "risk_assessment", None)
        if assessment is None:
            return Response(
                {"detail": "No risk assessment available for this transaction."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(RiskAssessmentSerializer(_assessment_to_dict(assessment)).data)


def _assessment_to_dict(assessment):
    return {
        "transaction_id": assessment.transaction.transaction_id,
        "ml_score": assessment.ml_score,
        "rule_score": assessment.rule_score,
        "behavioral_score": assessment.behavioral_score,
        "graph_score": assessment.graph_score,
        "final_score": assessment.final_score,
        "risk_category": assessment.risk_category,
        "confidence": assessment.confidence,
        "recommended_action": assessment.recommended_action,
        "model_version": assessment.model_version,
        "created_at": assessment.created_at,
    }


class InvestigatorActionSerializer(serializers.Serializer):
    ACTION_CHOICES = ["monitor", "manual_review", "escalate", "dismissed"]
    action = serializers.ChoiceField(choices=ACTION_CHOICES)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class TransactionActionView(APIView):
    """
    POST /api/transactions/{id}/action/

    Records the investigator's final decision. This is the ONLY place a
    human-facing action gets committed - the LLM assistant can discuss and
    recommend, but never calls this endpoint itself. Bounded to a small,
    reversible action vocabulary; nothing here can move money or lock an
    account irreversibly (see ARCHITECTURE.md / LLM.md "Safety" section).
    """

    def post(self, request, transaction_id):
        txn = get_object_or_404(Transaction, transaction_id=transaction_id)
        serializer = InvestigatorActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        log_audit_event(
            txn, actor="investigator", action="investigator_decision",
            new_state={"action": data["action"], "notes": data["notes"]},
        )
        return Response({"transaction_id": transaction_id, "recorded_action": data["action"]},
                         status=status.HTTP_201_CREATED)
