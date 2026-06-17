from django.urls import path

from .views import DepositView, LedgerView, WalletView, WithdrawView

urlpatterns = [
    path('wallet/', WalletView.as_view(), name='wallet'),
    path('wallet/ledger/', LedgerView.as_view(), name='wallet-ledger'),
    path('wallet/deposit/', DepositView.as_view(), name='wallet-deposit'),
    path('wallet/withdraw/', WithdrawView.as_view(), name='wallet-withdraw'),
]
