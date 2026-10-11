from django.urls import path

from .views import (
    AdminLedgerViewSet, AdminPaymentGatewayTestView, AdminPaymentGatewayView, AdminPaymentMethodViewSet,
    AdminWithdrawalSettingsView, AdminWithdrawalsView, DepositView, LedgerView, MyWithdrawalsView, PaymentMethodsView,
    PaymentStatusView, PaynowResultView, PSPWebhookView, WalletView, WithdrawView,
)

urlpatterns = [
    path('wallet/', WalletView.as_view(), name='wallet'),
    path('wallet/ledger/', LedgerView.as_view(), name='wallet-ledger'),
    path('wallet/deposit/', DepositView.as_view(), name='wallet-deposit'),
    path('wallet/withdraw/', WithdrawView.as_view(), name='wallet-withdraw'),
    path('wallet/withdrawals/', MyWithdrawalsView.as_view(), name='wallet-withdrawals'),
    path('wallet/withdrawals/<int:pk>/cancel/', MyWithdrawalsView.as_view(), name='wallet-withdrawal-cancel'),
    path('admin/withdrawals/', AdminWithdrawalsView.as_view(), name='admin-withdrawals'),
    path('admin/withdrawals/<int:pk>/mark-paid/', AdminWithdrawalsView.as_view(action='paid'), name='admin-withdrawal-paid'),
    path('admin/withdrawals/<int:pk>/reject/', AdminWithdrawalsView.as_view(action='reject'), name='admin-withdrawal-reject'),
    path('admin/withdrawal-settings/', AdminWithdrawalSettingsView.as_view(), name='admin-withdrawal-settings'),
    path('wallet/deposits/<str:reference>/', PaymentStatusView.as_view(), name='wallet-deposit-status'),
    path('wallet/paynow/result/', PaynowResultView.as_view(), name='wallet-paynow-result'),
    path('wallet/webhook/<str:provider>/', PSPWebhookView.as_view(), name='wallet-webhook'),
    path('admin/ledger/', AdminLedgerViewSet.as_view({'get': 'list'}), name='admin-ledger'),
    path('wallet/payment-methods/', PaymentMethodsView.as_view(), name='wallet-payment-methods'),
    path('admin/payment-gateway/', AdminPaymentGatewayView.as_view(), name='admin-payment-gateway'),
    path('admin/payment-gateway/test/', AdminPaymentGatewayTestView.as_view(), name='admin-payment-gateway-test'),
    path('admin/payment-methods/', AdminPaymentMethodViewSet.as_view({'get': 'list', 'post': 'create'}),
         name='admin-payment-methods'),
    path('admin/payment-methods/<int:pk>/', AdminPaymentMethodViewSet.as_view({
        'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy',
    }), name='admin-payment-method'),
]
