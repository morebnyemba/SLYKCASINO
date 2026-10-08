from django.urls import path

from .views import (
    AdminLedgerViewSet, AdminPaymentMethodViewSet, DepositView, LedgerView, PaymentMethodsView, PaymentStatusView,
    PaynowResultView, PSPWebhookView, WalletView, WithdrawView,
)

urlpatterns = [
    path('wallet/', WalletView.as_view(), name='wallet'),
    path('wallet/ledger/', LedgerView.as_view(), name='wallet-ledger'),
    path('wallet/deposit/', DepositView.as_view(), name='wallet-deposit'),
    path('wallet/withdraw/', WithdrawView.as_view(), name='wallet-withdraw'),
    path('wallet/deposits/<str:reference>/', PaymentStatusView.as_view(), name='wallet-deposit-status'),
    path('wallet/paynow/result/', PaynowResultView.as_view(), name='wallet-paynow-result'),
    path('wallet/webhook/<str:provider>/', PSPWebhookView.as_view(), name='wallet-webhook'),
    path('admin/ledger/', AdminLedgerViewSet.as_view({'get': 'list'}), name='admin-ledger'),
    path('wallet/payment-methods/', PaymentMethodsView.as_view(), name='wallet-payment-methods'),
    path('admin/payment-methods/', AdminPaymentMethodViewSet.as_view({'get': 'list', 'post': 'create'}),
         name='admin-payment-methods'),
    path('admin/payment-methods/<int:pk>/', AdminPaymentMethodViewSet.as_view({
        'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy',
    }), name='admin-payment-method'),
]
