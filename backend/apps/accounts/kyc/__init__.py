"""KYC (Know Your Customer) provider module registry.

Usage:
    from apps.accounts.kyc import get_kyc_provider
    kyc = get_kyc_provider()  # uses settings.KYC_PROVIDER, defaults to 'stub'
    session = kyc.create_session(player_id, first_name, last_name, email)
"""
from .registry import get_kyc_provider, list_providers, register  # noqa: F401
from . import stub  # noqa: F401 — ensures StubKYCProvider is registered at import time

__all__ = ['get_kyc_provider', 'list_providers', 'register']
