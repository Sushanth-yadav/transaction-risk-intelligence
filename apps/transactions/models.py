"""
Core entity models for RazorGuard.

Design note: every entity has a synthetic, opaque external identifier
(customer_id, device_id, etc.) separate from the Django primary key. This
mirrors how a real payments platform would reference entities across
systems (tokenized identifiers, not raw PII), and keeps the graph/relationship
layer (apps.graph, built on top of these FKs) simple to reason about.

No real personal or financial data is stored anywhere in this schema -
this project uses synthetic data only.
"""

from django.db import models


class Customer(models.Model):
    customer_id = models.CharField(max_length=64, unique=True, db_index=True)
    account_age_days = models.IntegerField(default=0)
    # long-run behavioral profile, used as a fallback when a customer has
    # too little transaction history for expanding-window stats to be reliable
    avg_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    home_location = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.customer_id


class Device(models.Model):
    device_id = models.CharField(max_length=64, unique=True, db_index=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.device_id


class IPAddress(models.Model):
    ip_id = models.CharField(max_length=64, unique=True, db_index=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.ip_id


class PaymentInstrument(models.Model):
    instrument_id = models.CharField(max_length=64, unique=True, db_index=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.instrument_id


class Merchant(models.Model):
    merchant_id = models.CharField(max_length=64, unique=True, db_index=True)
    category = models.CharField(max_length=64, blank=True)

    def __str__(self):
        return self.merchant_id


class Transaction(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ("card", "Card"),
        ("upi", "UPI"),
        ("netbanking", "Net Banking"),
        ("wallet", "Wallet"),
    ]

    transaction_id = models.CharField(max_length=64, unique=True, db_index=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="transactions")
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name="transactions")
    device = models.ForeignKey(Device, on_delete=models.PROTECT, related_name="transactions")
    ip_address = models.ForeignKey(IPAddress, on_delete=models.PROTECT, related_name="transactions")
    payment_instrument = models.ForeignKey(
        PaymentInstrument, on_delete=models.PROTECT, related_name="transactions"
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    timestamp = models.DateTimeField(db_index=True)
    location = models.CharField(max_length=64)
    payment_method = models.CharField(max_length=16, choices=PAYMENT_METHOD_CHOICES)

    # ground-truth label, only ever populated from synthetic training data /
    # manual investigator confirmation - NEVER used as a live scoring input
    fraud_label = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["customer", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.transaction_id} (₹{self.amount})"
