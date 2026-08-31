"""
Tests for apps.graph.services against a real (SQLite test) database, since
graph analysis is fundamentally a set of DB queries feeding NetworkX.
"""

from datetime import datetime, timezone

from django.test import TestCase

from apps.graph.services import analyze_relationships
from apps.transactions.models import Customer, Device, IPAddress, Merchant, PaymentInstrument, Transaction


def _make_transaction(customer_id, device_id, ip_id, ts, amount=500):
    customer, _ = Customer.objects.get_or_create(customer_id=customer_id, defaults={"account_age_days": 100})
    device, _ = Device.objects.get_or_create(device_id=device_id)
    ip, _ = IPAddress.objects.get_or_create(ip_id=ip_id)
    merchant, _ = Merchant.objects.get_or_create(merchant_id="merch_test", defaults={"category": "grocery"})
    instrument, _ = PaymentInstrument.objects.get_or_create(instrument_id=f"pmt_{customer_id}")
    return Transaction.objects.create(
        transaction_id=f"txn_{customer_id}_{ts.timestamp()}",
        customer=customer, merchant=merchant, device=device, ip_address=ip,
        payment_instrument=instrument, amount=amount, timestamp=ts,
        location="Mumbai", payment_method="card",
    )


class GraphAnalysisTests(TestCase):
    def test_isolated_customer_has_no_connections(self):
        _make_transaction("cust_a", "dev_a", "ip_a", datetime(2026, 1, 1, tzinfo=timezone.utc))
        result = analyze_relationships("cust_a", "dev_a", "ip_a")
        self.assertEqual(result["connected_customers"], [])
        self.assertFalse(result["is_suspicious_cluster"])

    def test_two_customers_sharing_one_device_is_not_yet_a_cluster(self):
        # is_suspicious_cluster requires >= 2 OTHER connected customers (3 total)
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        _make_transaction("cust_a", "dev_shared", "ip_a", ts)
        _make_transaction("cust_b", "dev_shared", "ip_b", ts)
        result = analyze_relationships("cust_a", "dev_shared", "ip_a")
        self.assertEqual(result["connected_customers"], ["cust_b"])
        self.assertFalse(result["is_suspicious_cluster"])

    def test_fraud_ring_of_three_plus_is_flagged(self):
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        _make_transaction("cust_a", "dev_ring", "ip_a", ts)
        _make_transaction("cust_b", "dev_ring", "ip_b", ts)
        _make_transaction("cust_c", "dev_ring", "ip_c", ts)

        result = analyze_relationships("cust_a", "dev_ring", "ip_a")
        self.assertTrue(result["is_suspicious_cluster"])
        self.assertEqual(sorted(result["connected_customers"]), ["cust_b", "cust_c"])
        self.assertEqual(result["component_size"], 3)

    def test_causal_cutoff_ignores_future_transactions(self):
        early = datetime(2026, 1, 1, tzinfo=timezone.utc)
        late = datetime(2026, 6, 1, tzinfo=timezone.utc)
        _make_transaction("cust_a", "dev_ring", "ip_a", early)
        # cust_b and cust_c only join the ring AFTER cust_a's transaction
        _make_transaction("cust_b", "dev_ring", "ip_b", late)
        _make_transaction("cust_c", "dev_ring", "ip_c", late)

        # scoring cust_a's early transaction should NOT see the future ring
        result = analyze_relationships("cust_a", "dev_ring", "ip_a", timestamp_cutoff=early)
        self.assertEqual(result["connected_customers"], [])

        # but a full (non-causal) investigation view sees everything
        result_full = analyze_relationships("cust_a", "dev_ring", "ip_a", timestamp_cutoff=None)
        self.assertTrue(result_full["is_suspicious_cluster"])
