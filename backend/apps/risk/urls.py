from django.urls import path

from .views import CasesBulkView, CasesView, CaseView, PlayerRiskView, SettingsView

urlpatterns = [
    path('admin/risk/cases/', CasesView.as_view(), name='risk-cases'),
    path('admin/risk/cases/bulk/', CasesBulkView.as_view(), name='risk-cases-bulk'),
    path('admin/risk/cases/<int:pk>/', CaseView.as_view(), name='risk-case'),
    path('admin/risk/cases/<int:pk>/decide/', CaseView.as_view(), name='risk-case-decide'),
    path('admin/risk/players/<int:pk>/', PlayerRiskView.as_view(), name='risk-player'),
    path('admin/risk/settings/', SettingsView.as_view(), name='risk-settings'),
]
