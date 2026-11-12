from django.urls import path

from .views import (
    AuditFileView, AuditSignView, AuditsView, AuditUploadView, DecideWithdrawalView, ExpensesView, ExpenseView, OverviewView,
    PoolDayView, PoolLedgerView, SettingsView, WithdrawView,
)

urlpatterns = [
    path('admin/revenue-share/', OverviewView.as_view(), name='revenue-overview'),
    path('admin/revenue-share/withdraw/', WithdrawView.as_view(), name='revenue-withdraw'),
    path('admin/revenue-share/withdrawals/<int:pk>/decide/', DecideWithdrawalView.as_view(), name='revenue-decide'),
    path('admin/revenue-share/expenses/', ExpensesView.as_view(), name='revenue-expenses'),
    path('admin/revenue-share/expenses/<int:pk>/', ExpenseView.as_view(), name='revenue-expense'),
    path('admin/revenue-share/settings/', SettingsView.as_view(), name='revenue-settings'),
    path('admin/revenue-share/pool/', PoolLedgerView.as_view(), name='revenue-pool'),
    path('admin/revenue-share/pool/days/<str:day>/', PoolDayView.as_view(), name='revenue-pool-day'),
    path('admin/revenue-share/audits/', AuditsView.as_view(), name='revenue-audits'),
    path('admin/revenue-share/audits/<str:week>/upload/', AuditUploadView.as_view(), name='revenue-audit-upload'),
    path('admin/revenue-share/audits/<str:week>/sign/', AuditSignView.as_view(), name='revenue-audit-sign'),
    path('admin/revenue-share/audits/<str:week>/file/<str:kind>/', AuditFileView.as_view(), name='revenue-audit-file'),
]
