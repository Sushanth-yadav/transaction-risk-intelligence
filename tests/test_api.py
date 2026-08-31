"""
End-to-end API tests: POST a transaction, confirm it runs through the full
risk pipeline (ML + rules + behavioral + graph) and produces a persisted,
retrievable risk assessment, evidence, and audit trail. Requires a trained
model at ml/models/random_forest.joblib (run ml/training/train_and_evaluate.py
first if this fails with FileNotFoundError).
"""

from rest_framework.test import APITestCase


class TransactionAPITests(APITestCase):
    def _post_transaction(self, **overrides):
        payload = {
            "transaction_id": "txn_api_test_001",
            "customer_id": "cust_api_test_001",
            "merchant_id": "merch_api_test_001",
            "device_id": "dev_api_test_001",
            "ip_id": "ip_api_test_001",
            "payment_instrument_id": "pmt_api_test_001",
            "amount": "1200.00",
            "timestamp": "2026-03-01T10:00:00Z",
            "location": "Bengaluru",
            "payment_method": "card",
        }
        payload.update(overrides)
        return self.client.post("/api/transactions/", payload, format="json")

    def test_create_transaction_returns_risk_assessment(self):
        response = self._post_transaction()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertIn("risk_assessment", body)
        self.assertIsNotNone(body["risk_assessment"])
        self.assertIn(body["risk_assessment"]["risk_category"], ["low", "medium", "high"])

    def test_duplicate_transaction_id_is_rejected(self):
        self._post_transaction(transaction_id="txn_api_test_dup")
        response = self._post_transaction(transaction_id="txn_api_test_dup")
        self.assertEqual(response.status_code, 400)

    def test_risk_endpoint_returns_persisted_assessment(self):
        self._post_transaction(transaction_id="txn_api_test_002")
        response = self.client.get("/api/transactions/txn_api_test_002/risk/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("final_score", response.json())

    def test_evidence_endpoint_returns_evidence_bundle(self):
        self._post_transaction(transaction_id="txn_api_test_003")
        response = self.client.get("/api/transactions/txn_api_test_003/evidence/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("evidence", response.json())

    def test_audit_trail_records_scoring_event(self):
        self._post_transaction(transaction_id="txn_api_test_004")
        response = self.client.get("/api/transactions/txn_api_test_004/audit/")
        self.assertEqual(response.status_code, 200)
        actions = [e["action"] for e in response.json()]
        self.assertIn("risk_scored", actions)

    def test_unscored_risk_lookup_returns_404_for_unknown_transaction(self):
        response = self.client.get("/api/transactions/txn_does_not_exist/risk/")
        self.assertEqual(response.status_code, 404)

    def test_investigator_action_is_recorded(self):
        self._post_transaction(transaction_id="txn_api_test_005")
        response = self.client.post(
            "/api/transactions/txn_api_test_005/action/",
            {"action": "escalate", "notes": "Escalating for manual review."},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        audit = self.client.get("/api/transactions/txn_api_test_005/audit/").json()
        actions = [e["action"] for e in audit]
        self.assertIn("investigator_decision", actions)
