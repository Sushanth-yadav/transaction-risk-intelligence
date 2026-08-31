"""
RiskAssessment: the aggregated output of the scoring pipeline for one
transaction. This is deliberately a single row per transaction holding
each sub-system's contribution (ml, rules, behavioral, graph) PLUS the
final aggregated score - so an investigator (or the LLM, via a tool call)
can see not just "the score" but "which sub-system drove it."
"""

from django.db import models

from apps.transactions.models import Transaction


class RiskAssessment(models.Model):
    RISK_CATEGORY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
    ]
    CONFIDENCE_CHOICES = [
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]

    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE, related_name="risk_assessment")

    # sub-system scores, each 0-100, so they're independently interpretable
    ml_score = models.FloatField(help_text="RandomForest fraud probability, scaled 0-100")
    rule_score = models.FloatField(default=0, help_text="Deterministic rule engine contribution, 0-100")
    behavioral_score = models.FloatField(default=0, help_text="Behavioral anomaly contribution, 0-100")
    graph_score = models.FloatField(default=0, help_text="Relationship/graph anomaly contribution, 0-100")

    final_score = models.FloatField(help_text="Aggregated risk score, 0-100")
    risk_category = models.CharField(max_length=8, choices=RISK_CATEGORY_CHOICES)
    confidence = models.CharField(max_length=8, choices=CONFIDENCE_CHOICES, default="medium")

    model_version = models.CharField(max_length=32, default="random_forest_v1")
    recommended_action = models.CharField(max_length=32, default="monitor")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["risk_category"])]

    def __str__(self):
        return f"{self.transaction.transaction_id}: {self.risk_category} ({self.final_score:.1f})"
