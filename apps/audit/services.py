"""
Single entry point for writing audit events. Every part of the system
(risk pipeline, investigation assistant, investigator action endpoint)
calls this rather than creating AuditLog rows directly - keeps the audit
trail consistent and makes it trivial to find every write site later.
"""

from .models import AuditLog


def log_audit_event(
    transaction,
    actor: str,
    action: str,
    previous_state=None,
    new_state=None,
):
    """
    Record an audit event for a transaction.
    """

    return AuditLog.objects.create(
        transaction=transaction,
        actor=actor,
        action=action,
        previous_state=previous_state or {},
        new_state=new_state or {},
    )