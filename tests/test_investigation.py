"""
Tests for apps.investigation.tools - the backend-controlled functions the
LLM can call. These don't require a live Anthropic API key: they test that
tools return a clean {"error": ...} for missing data (the mechanism that
lets the LLM say "insufficient evidence" instead of hallucinating), and
that the real data path returns exactly what's in the DB.
"""

from datetime import datetime, timezone

from django.test import TestCase

from apps.investigation import tools
from apps.transactions.models import Customer, Device, IPAddress, Merchant, PaymentInstrument, Transaction


class InvestigationToolsTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(customer_id="cust_x", account_age_days=200, avg_amount=500)
        self.merchant = Merchant.objects.create(merchant_id="merch_x", category="electronics")
        self.device = Device.objects.create(device_id="dev_x")
        self.ip = IPAddress.objects.create(ip_id="ip_x")
        self.instrument = PaymentInstrument.objects.create(instrument_id="pmt_x")
        self.txn = Transaction.objects.create(
            transaction_id="txn_x", customer=self.customer, merchant=self.merchant,
            device=self.device, ip_address=self.ip, payment_instrument=self.instrument,
            amount=1500, timestamp=datetime(2026, 3, 1, tzinfo=timezone.utc),
            location="Delhi", payment_method="card",
        )

    def test_get_transaction_returns_error_for_unknown_id(self):
        result = tools.get_transaction("txn_does_not_exist")
        self.assertIn("error", result)

    def test_get_transaction_returns_real_data(self):
        result = tools.get_transaction("txn_x")
        self.assertEqual(result["customer_id"], "cust_x")
        self.assertEqual(result["amount"], 1500.0)
        self.assertEqual(result["location"], "Delhi")

    def test_get_customer_history_returns_error_for_unknown_customer(self):
        result = tools.get_customer_history("cust_does_not_exist")
        self.assertIn("error", result)

    def test_get_customer_history_summarizes_correctly(self):
        result = tools.get_customer_history("cust_x")
        self.assertEqual(result["total_transactions"], 1)
        self.assertEqual(result["average_amount"], 1500.0)

    def test_get_risk_evidence_without_assessment_returns_error(self):
        # no RiskAssessment created for this transaction yet
        result = tools.get_risk_evidence("txn_x")
        self.assertIn("error", result)

    def test_get_audit_history_empty_is_not_an_error(self):
        result = tools.get_audit_history("txn_x")
        self.assertEqual(result["events"], [])
