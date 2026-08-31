from django.contrib import admin
from django.urls import path, include

from apps.dashboard.views import DashboardSummaryAPIView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/dashboard/summary/", DashboardSummaryAPIView.as_view(), name="dashboard-summary"),
    path("api/", include("apps.transactions.urls")),
    path("api/", include("apps.evidence.urls")),
    path("api/", include("apps.investigation.urls")),
    path("api/", include("apps.audit.urls")),
    path("", include("apps.dashboard.urls")),
]
