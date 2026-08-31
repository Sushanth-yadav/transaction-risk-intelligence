from django.urls import path

from .views import dashboard_home, transaction_detail

urlpatterns = [
    path("", dashboard_home, name="dashboard-home"),
    path("transactions/<str:transaction_id>/", transaction_detail, name="dashboard-transaction-detail"),
]
