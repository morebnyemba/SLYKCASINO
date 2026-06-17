# To enable: pip install stripe, set PSP_PROVIDER=stripe in env
# Uncomment the @register decorator below.
import os
from decimal import Decimal

from .base import BasePSP, PaymentIntent, PaymentResult
from .registry import register


# @register('stripe')
class StripePSP(BasePSP):
    """Stripe Payment Intents integration skeleton.

    To activate:
    1. pip install stripe
    2. Set PSP_PROVIDER=stripe in your .env
    3. Set STRIPE_SECRET_KEY=sk_... in your .env
    4. Uncomment @register('stripe') above
    5. Wire the webhook endpoint in urls.py
    """

    def __init__(self):
        import stripe
        stripe.api_key = os.environ['STRIPE_SECRET_KEY']
        self.stripe = stripe

    def create_deposit_intent(self, amount, currency, player_id, idempotency_key):
        intent = self.stripe.PaymentIntent.create(
            amount=int(amount * 100),  # Stripe uses cents
            currency=currency.lower(),
            metadata={'player_id': player_id},
            idempotency_key=idempotency_key,
        )
        return PaymentIntent(
            provider_ref=intent['id'],
            redirect_url=intent.get('next_action', {}).get('redirect_to_url', {}).get('url', ''),
            status='pending',
            amount=amount,
            currency=currency,
        )

    def create_withdrawal(self, amount, currency, player_id, destination, idempotency_key):
        # Stripe Payouts (requires connected account)
        raise NotImplementedError('Configure Stripe Connect for payouts')

    def verify_webhook(self, payload, signature):
        event = self.stripe.Webhook.construct_event(
            payload, signature, os.environ['STRIPE_WEBHOOK_SECRET'],
        )
        pi = event['data']['object']
        status = 'completed' if event['type'] == 'payment_intent.succeeded' else 'failed'
        return PaymentResult(
            provider_ref=pi['id'],
            status=status,
            amount=Decimal(pi['amount']) / 100,
            currency=pi['currency'].upper(),
            raw=event,
        )
