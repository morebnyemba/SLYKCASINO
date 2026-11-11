from django.urls import path

from .views import DecideWithdrawalView, ExpensesView, ExpenseView, OverviewView, SettingsView, WithdrawView

urlpatterns = [
    path('admin/revenue-share/', OverviewView.as_view(), name='revenue-overview'),
    path('admin/revenue-share/withdraw/', WithdrawView.as_view(), name='revenue-withdraw'),
    path('admin/revenue-share/withdrawals/<int:pk>/decide/', DecideWithdrawalView.as_view(), name='revenue-decide'),
    path('admin/revenue-share/expenses/', ExpensesView.as_view(), name='revenue-expenses'),
    path('admin/revenue-share/expenses/<int:pk>/', ExpenseView.as_view(), name='revenue-expense'),
    path('admin/revenue-share/settings/', SettingsView.as_view(), name='revenue-settings'),
]
