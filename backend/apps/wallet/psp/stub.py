import uuid
from decimal import Decimal

from .base import BasePSP, PaymentIntent, PaymentResult
from .registry import register


@register('stub')
class StubPSP(BasePSP):
    """No-op provider for development and testing. Auto-completes all transactions."""

    def create_deposit_intent(self, amount, currency, player_id, idempotency_key):
        return PaymentIntent(
            provider_ref=f'stub_{uuid.uuid4().hex}',
            redirect_url='',
            status='completed',
            amount=amount,
            currency=currency,
        )

    def create_withdrawal(self, amount, currency, player_id, destination, idempotency_key):
        return PaymentResult(
            provider_ref=f'stub_{uuid.uuid4().hex}',
            status='completed',
            amount=amount,
            currency=currency,
            raw={},
        )

    def verify_webhook(self, payload, signature):
        raise NotImplementedError('StubPSP does not handle webhooks')
