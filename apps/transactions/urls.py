from django.urls import path

from .views import TransactionActionView, TransactionDetailView, TransactionListCreateView, TransactionRiskView

urlpatterns = [
    path("transactions/", TransactionListCreateView.as_view(), name="transaction-list-create"),
    path("transactions/<str:transaction_id>/", TransactionDetailView.as_view(), name="transaction-detail"),
    path("transactions/<str:transaction_id>/risk/", TransactionRiskView.as_view(), name="transaction-risk"),
    path("transactions/<str:transaction_id>/action/", TransactionActionView.as_view(), name="transaction-action"),
]
