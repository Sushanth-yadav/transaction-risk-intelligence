from django.urls import path

from .views import TransactionAuditView

urlpatterns = [
    path("transactions/<str:transaction_id>/audit/", TransactionAuditView.as_view(), name="transaction-audit"),
]
