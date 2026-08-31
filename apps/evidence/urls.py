from django.urls import path

from .views import TransactionEvidenceView, TransactionRelatedEntitiesView

urlpatterns = [
    path("transactions/<str:transaction_id>/evidence/", TransactionEvidenceView.as_view(), name="transaction-evidence"),
    path("transactions/<str:transaction_id>/related/", TransactionRelatedEntitiesView.as_view(), name="transaction-related"),
]
