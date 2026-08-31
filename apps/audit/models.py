"""
AuditLog: an append-only record of everything that happens to a
transaction after ingestion - scoring, investigation queries, and any
investigator decision. This is what makes the system's decisions
reviewable after the fact, which is a hard requirement for any real
financial risk system, not just a nice-to-have.

Rows are never updated or deleted through the application - only created.
"""

from django.db import models

from apps.transactions.models import Transaction


class AuditLog(models.Model):
    ACTOR_CHOICES = [
        ("system", "System"),
        ("investigator", "Investigator"),
        ("llm_assistant", "LLM Assistant"),
    ]

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="audit_logs")
    actor = models.CharField(max_length=16, choices=ACTOR_CHOICES)
    action = models.CharField(max_length=64)
    previous_state = models.JSONField(null=True, blank=True)
    new_state = models.JSONField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.transaction.transaction_id}: {self.actor} -> {self.action}"
