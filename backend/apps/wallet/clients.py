"""wallet external interfaces — payment service provider (PSP) normalization."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class PspResult:
    """Normalized PSP response (provider-agnostic)."""
    success: bool
    provider_ref: str
    raw_status: str


class PaymentProviderClient:
    """Interface to an external PSP for deposits/withdrawals.

    Concrete HTTP omitted; the contract is a normalized :class:`PspResult` so the
    service layer never sees provider-specific payloads. Each call carries the
    wallet idempotency key so the PSP and our ledger stay in lock-step on retry.
    """

    provider_name = 'stub-psp'

    def charge(self, player_id: int, amount: Decimal, idempotency_key: str) -> PspResult:
        raw = self._call(player_id, amount, idempotency_key, op='charge')
        return self._normalize(raw)

    def payout(self, player_id: int, amount: Decimal, idempotency_key: str) -> PspResult:
        raw = self._call(player_id, amount, idempotency_key, op='payout')
        return self._normalize(raw)

    # -- internals ---------------------------------------------------------
    def _call(self, player_id: int, amount: Decimal, key: str, op: str) -> dict[str, Any]:
        return {'status': 'ok', 'ref': f'{op}-{key}'}

    def _normalize(self, raw: dict[str, Any]) -> PspResult:
        status = raw.get('status', 'unknown')
        return PspResult(success=status == 'ok', provider_ref=str(raw.get('ref', '')), raw_status=status)
