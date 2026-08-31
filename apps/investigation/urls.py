from django.urls import path

from .views import InvestigationAskView

urlpatterns = [
    path("investigate/<str:transaction_id>/ask/", InvestigationAskView.as_view(), name="investigation-ask"),
]
