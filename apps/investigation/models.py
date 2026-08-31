"""
InvestigationLog: records every natural-language question an investigator
asked the LLM assistant about a transaction, which tools were called to
answer it, and the grounded answer given - itself part of the audit trail.
Built out Day 2 alongside the LLM orchestrator.
"""

from django.db import models

from apps.transactions.models import Transaction


class InvestigationLog(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="investigation_logs")
    question = models.TextField()
    answer = models.TextField()
    tools_called = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
