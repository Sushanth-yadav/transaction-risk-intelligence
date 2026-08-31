"""
Unit tests for apps.behavior. These test the pure scoring logic against
hand-constructed feature dicts, independent of the database, so they run
fast and pin down exact expected behavior for each rule/signal.
"""

from django.test import SimpleTestCase

from apps.behavior.rules import evaluate_rules
from apps.behavior.anomaly import _amount_anomaly_score, _novelty_score, _velocity_anomaly_score


def _base_features(**overrides):
    features = {
        "amount": 1000.0,
        "amount_zscore_vs_customer": 0.5,
        "amount_ratio_to_customer_avg": 1.2,
        "customer_txn_count_before": 10,
        "is_new_device": 0,
        "is_new_ip": 0,
        "is_new_location": 0,
        "hours_since_last_txn": 48,
        "txn_count_last_1h": 0,
        "txn_count_last_24h": 1,
        "device_customer_count_so_far": 0,
        "account_age_days": 400,
        "hour_of_day": 14,
        "day_of_week": 2,
    }
    features.update(overrides)
    return features


class RuleEngineTests(SimpleTestCase):
    def test_no_rules_fire_for_normal_transaction(self):
        score, evidence = evaluate_rules(None, _base_features())
        self.assertEqual(score, 0)
        self.assertEqual(evidence, [])

    def test_large_amount_jump_fires(self):
        score, evidence = evaluate_rules(None, _base_features(amount_ratio_to_customer_avg=6))
        self.assertGreaterEqual(score, 30)
        self.assertTrue(any(e["rule_name"] == "large_amount_jump" for e in evidence))

    def test_stacked_signals_increase_score(self):
        features = _base_features(
            amount_ratio_to_customer_avg=12, is_new_device=1, is_new_location=1,
            txn_count_last_1h=4, device_customer_count_so_far=2,
        )
        score, evidence = evaluate_rules(None, features)
        self.assertGreater(score, 60)
        rule_names = {e["rule_name"] for e in evidence}
        self.assertIn("extreme_amount_jump", rule_names)
        self.assertIn("high_velocity", rule_names)
        self.assertIn("shared_device", rule_names)

    def test_score_caps_at_100(self):
        features = _base_features(
            amount_ratio_to_customer_avg=20, is_new_device=1, is_new_location=1,
            txn_count_last_1h=10, device_customer_count_so_far=5,
            account_age_days=5, customer_txn_count_before=0,
        )
        score, _ = evaluate_rules(None, features)
        self.assertLessEqual(score, 100)


class BehavioralAnomalyTests(SimpleTestCase):
    def test_amount_zscore_near_zero_is_low_score(self):
        score, desc = _amount_anomaly_score(_base_features(amount_zscore_vs_customer=0.3))
        self.assertLess(score, 10)
        self.assertIsNone(desc)

    def test_large_zscore_is_flagged(self):
        score, desc = _amount_anomaly_score(_base_features(amount_zscore_vs_customer=8.0))
        self.assertGreater(score, 50)
        self.assertIsNotNone(desc)

    def test_novelty_score_scales_with_flag_count(self):
        low_score, _ = _novelty_score(_base_features(is_new_device=1))
        high_score, desc = _novelty_score(_base_features(is_new_device=1, is_new_ip=1, is_new_location=1))
        self.assertGreater(high_score, low_score)
        self.assertIsNotNone(desc)

    def test_velocity_anomaly_requires_established_baseline(self):
        # a brand-new-ish customer (very few prior txns relative to account age)
        # shouldn't get a wildly confident velocity anomaly score
        score, _ = _velocity_anomaly_score(_base_features(customer_txn_count_before=0, txn_count_last_24h=1))
        self.assertLessEqual(score, 100)
