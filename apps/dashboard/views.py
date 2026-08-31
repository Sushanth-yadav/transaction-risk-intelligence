from django.db.models import Avg, Count, Max, Min, Sum
from django.shortcuts import get_object_or_404, render
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.evidence.models import Evidence
from apps.graph.services import analyze_relationships
from apps.risk.models import RiskAssessment
from apps.transactions.models import Transaction


# ---------------------------------------------------------
# TRUSTED TRANSACTION THRESHOLD
# ---------------------------------------------------------
# Transactions below this score are considered trusted
# activity for the dashboard.
TRUSTED_RISK_THRESHOLD = 5


class DashboardSummaryAPIView(APIView):
    """GET /api/dashboard/summary/ - counts by risk category, totals."""

    def get(self, request):
        total = Transaction.objects.count()

        by_category = dict(
            RiskAssessment.objects
            .values_list("risk_category")
            .annotate(n=Count("id"))
        )

        scored = RiskAssessment.objects.count()

        trusted_count = RiskAssessment.objects.filter(
            final_score__lt=TRUSTED_RISK_THRESHOLD
        ).count()

        return Response({
            "total_transactions": total,
            "scored_transactions": scored,
            "unscored_transactions": total - scored,
            "high_risk": by_category.get("high", 0),
            "medium_risk": by_category.get("medium", 0),
            "low_risk": by_category.get("low", 0),
            "trusted_transactions": trusted_count,
        })


def dashboard_home(request):

    risk_filter = request.GET.get("risk_category", "")

    # -----------------------------------------------------
    # BASE TRANSACTION QUERY
    # -----------------------------------------------------

    qs = (
        Transaction.objects
        .select_related(
            "customer",
            "risk_assessment",
        )
        .order_by("-timestamp")
    )

    # -----------------------------------------------------
    # FILTERS
    # -----------------------------------------------------

    if risk_filter == "no_risk":

        qs = qs.filter(
            risk_assessment__isnull=False,
            risk_assessment__final_score__lt=TRUSTED_RISK_THRESHOLD,
        )

    elif risk_filter in {"high", "medium", "low"}:

        qs = qs.filter(
            risk_assessment__risk_category=risk_filter
        )

    transactions = qs[:100]

    # -----------------------------------------------------
    # SUMMARY COUNTS
    # -----------------------------------------------------

    total = Transaction.objects.count()

    by_category = dict(
        RiskAssessment.objects
        .values_list("risk_category")
        .annotate(n=Count("id"))
    )

    # Trusted = extremely low risk, not necessarily literal 0.
    no_risk_count = RiskAssessment.objects.filter(
        final_score__lt=TRUSTED_RISK_THRESHOLD
    ).count()

    # -----------------------------------------------------
    # TRUSTED CUSTOMER GROUPS
    # -----------------------------------------------------

    trusted_groups = []

    if risk_filter == "no_risk":

        grouped = (
            qs.values("customer__customer_id")
            .annotate(
                transaction_count=Count("id"),
                total_amount=Sum("amount"),
                average_amount=Avg("amount"),
                first_activity=Min("timestamp"),
                last_activity=Max("timestamp"),
            )
            .order_by(
                "-transaction_count",
                "-total_amount",
            )
        )

        for group in grouped:

            customer_id = group["customer__customer_id"]

            activity = (
                Transaction.objects
                .filter(
                    customer__customer_id=customer_id,
                    risk_assessment__final_score__lt=TRUSTED_RISK_THRESHOLD,
                )
                .select_related(
                    "customer",
                    "merchant",
                    "device",
                    "ip_address",
                    "risk_assessment",
                )
                .order_by("-timestamp")[:25]
            )

            group["transactions"] = activity

            trusted_groups.append(group)

    # -----------------------------------------------------
    # RENDER DASHBOARD
    # -----------------------------------------------------

    return render(
        request,
        "dashboard/index.html",
        {
            "transactions": transactions,

            "risk_filter": risk_filter,

            "total": total,

            "high_count": by_category.get("high", 0),

            "medium_count": by_category.get("medium", 0),

            "low_count": by_category.get("low", 0),

            "no_risk_count": no_risk_count,

            "trusted_groups": trusted_groups,

            "trusted_threshold": TRUSTED_RISK_THRESHOLD,
        },
    )


def transaction_detail(request, transaction_id):

    txn = get_object_or_404(
        Transaction.objects.select_related(
            "customer",
            "merchant",
            "device",
            "ip_address",
        ),
        transaction_id=transaction_id,
    )

    assessment = getattr(
        txn,
        "risk_assessment",
        None,
    )

    if assessment:

        evidence_items = Evidence.objects.filter(
            risk_assessment=assessment
        )

    else:

        evidence_items = []

    audit_logs = (
        AuditLog.objects
        .filter(transaction=txn)
        .order_by("-timestamp")
    )

    related = analyze_relationships(
        txn.customer.customer_id,
        txn.device.device_id,
        txn.ip_address.ip_id,
    )

    return render(
        request,
        "dashboard/detail.html",
        {
            "txn": txn,
            "assessment": assessment,
            "evidence_items": evidence_items,
            "audit_logs": audit_logs,
            "related": related,
        },
    )