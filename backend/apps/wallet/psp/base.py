from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class PaymentIntent:
    provider_ref: str      # Provider's transaction ID
    redirect_url: str      # URL to redirect user to (if applicable)
    status: str            # 'pending' | 'completed' | 'failed'
    amount: Decimal
    currency: str


@dataclass
class PaymentResult:
    provider_ref: str
    status: str            # 'completed' | 'failed' | 'refunded'
    amount: Decimal
    currency: str
    raw: dict              # raw provider response


class BasePSP(ABC):
    """Abstract PSP. Implement this and register with @psp_registry.register('name')."""

    @abstractmethod
    def create_deposit_intent(
        self, amount: Decimal, currency: str, player_id: int, idempotency_key: str,
    ) -> PaymentIntent:
        """Initiate a deposit. Returns redirect URL or completes immediately."""

    @abstractmethod
    def create_withdrawal(
        self, amount: Decimal, currency: str, player_id: int,
        destination: dict, idempotency_key: str,
    ) -> PaymentResult:
        """Initiate a withdrawal to player's bank/wallet."""

    @abstractmethod
    def verify_webhook(self, payload: bytes, signature: str) -> PaymentResult:
        """Verify and parse an inbound webhook from the provider."""
