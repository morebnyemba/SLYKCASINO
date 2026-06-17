"""PSP (Payment Service Provider) module registry.

Usage:
    from apps.wallet.psp import get_psp
    psp = get_psp()  # uses settings.PSP_PROVIDER, defaults to 'stub'
    intent = psp.create_deposit_intent(amount, currency, player_id, key)
"""
from .registry import get_psp, list_providers, register  # noqa: F401
from . import stub  # noqa: F401 — ensures StubPSP is registered at import time

__all__ = ['get_psp', 'list_providers', 'register']
