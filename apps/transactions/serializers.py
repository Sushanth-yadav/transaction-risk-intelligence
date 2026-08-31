from rest_framework import serializers

from .models import Transaction


class TransactionCreateSerializer(serializers.Serializer):
    """
    Input serializer for POST /api/transactions/.

    Accepts external synthetic identifiers directly (customer_id, device_id,
    etc.) rather than Django PKs - callers (or our own seed script) never
    need to know internal database IDs, matching how a real ingestion
    endpoint would receive events from an upstream payments system.
    """

    transaction_id = serializers.CharField(max_length=64)
    customer_id = serializers.CharField(max_length=64)
    merchant_id = serializers.CharField(max_length=64)
    device_id = serializers.CharField(max_length=64)
    ip_id = serializers.CharField(max_length=64)
    payment_instrument_id = serializers.CharField(max_length=64)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    timestamp = serializers.DateTimeField()
    location = serializers.CharField(max_length=64)
    payment_method = serializers.ChoiceField(choices=Transaction.PAYMENT_METHOD_CHOICES)
    merchant_category = serializers.CharField(max_length=64, required=False, default="")
    account_age_days = serializers.IntegerField(required=False, default=0)
    customer_avg_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=0
    )

    def validate_transaction_id(self, value):
        if Transaction.objects.filter(transaction_id=value).exists():
            raise serializers.ValidationError("A transaction with this transaction_id already exists.")
        return value


class TransactionSerializer(serializers.ModelSerializer):
    customer_id = serializers.CharField(source="customer.customer_id", read_only=True)
    merchant_id = serializers.CharField(source="merchant.merchant_id", read_only=True)
    device_id = serializers.CharField(source="device.device_id", read_only=True)
    ip_id = serializers.CharField(source="ip_address.ip_id", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "transaction_id", "customer_id", "merchant_id", "device_id", "ip_id",
            "amount", "timestamp", "location", "payment_method", "created_at",
        ]


class RiskAssessmentSerializer(serializers.Serializer):
    transaction_id = serializers.CharField()
    ml_score = serializers.FloatField()
    rule_score = serializers.FloatField()
    behavioral_score = serializers.FloatField()
    graph_score = serializers.FloatField()
    final_score = serializers.FloatField()
    risk_category = serializers.CharField()
    confidence = serializers.CharField()
    recommended_action = serializers.CharField()
    model_version = serializers.CharField()
    created_at = serializers.DateTimeField()
