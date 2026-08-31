"""
Evidence: individual, human-readable reasons behind a risk assessment,
generated on Day 2 by the rule engine, behavioral detector, and graph
analyzer. Kept as discrete rows (rather than a single blob) so the
investigation API and LLM tool layer can retrieve/filter them granularly,
e.g. "show me only the graph-related evidence for this transaction."
"""

from django.db import models

from apps.risk.models import RiskAssessment


class Evidence(models.Model):
    EVIDENCE_TYPE_CHOICES = [
        ("rule", "Rule"),
        ("behavioral", "Behavioral"),
        ("graph", "Graph/Relationship"),
        ("model", "Model Explanation"),
    ]

    risk_assessment = models.ForeignKey(RiskAssessment, on_delete=models.CASCADE, related_name="evidence_items")
    evidence_type = models.CharField(max_length=16, choices=EVIDENCE_TYPE_CHOICES)
    description = models.TextField()
    structured_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.evidence_type}] {self.description[:60]}"
