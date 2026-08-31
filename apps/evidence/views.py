from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.graph.services import analyze_relationships
from apps.transactions.models import Transaction

from .models import Evidence


class EvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Evidence
        fields = ["evidence_type", "description", "structured_payload", "created_at"]


class TransactionEvidenceView(APIView):
    """GET /api/transactions/{id}/evidence/ - full evidence bundle backing the risk score."""

    def get(self, request, transaction_id):
        txn = get_object_or_404(Transaction, transaction_id=transaction_id)
        assessment = getattr(txn, "risk_assessment", None)
        if assessment is None:
            return Response({"detail": "No risk assessment available for this transaction."}, status=404)

        items = assessment.evidence_items.all()
        return Response({
            "transaction_id": transaction_id,
            "risk_category": assessment.risk_category,
            "final_score": assessment.final_score,
            "confidence": assessment.confidence,
            "sub_scores": {
                "ml_score": assessment.ml_score,
                "rule_score": assessment.rule_score,
                "behavioral_score": assessment.behavioral_score,
                "graph_score": assessment.graph_score,
            },
            "evidence": EvidenceSerializer(items, many=True).data,
        })


class TransactionRelatedEntitiesView(APIView):
    """GET /api/transactions/{id}/related/ - connected customers via shared device/IP (current, non-causal view)."""

    def get(self, request, transaction_id):
        txn = get_object_or_404(Transaction, transaction_id=transaction_id)
        result = analyze_relationships(
            txn.customer.customer_id, txn.device.device_id, txn.ip_address.ip_id, timestamp_cutoff=None
        )
        return Response({
            "transaction_id": transaction_id,
            "customer_id": txn.customer.customer_id,
            **result,
        })
