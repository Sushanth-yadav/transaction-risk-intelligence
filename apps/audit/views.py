from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from apps.transactions.models import Transaction
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ["actor", "action", "previous_state", "new_state", "timestamp"]


class TransactionAuditView(APIView):
    def get(self, request, transaction_id):
        txn = get_object_or_404(Transaction, transaction_id=transaction_id)
        logs = txn.audit_logs.all()
        return Response(AuditLogSerializer(logs, many=True).data)
