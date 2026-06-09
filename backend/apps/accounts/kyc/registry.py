from typing import Type

from .base import BaseKYCProvider

_registry: dict[str, Type[BaseKYCProvider]] = {}


def register(name: str):
    """Class decorator: @kyc_registry.register('onfido')"""
    def decorator(cls: Type[BaseKYCProvider]):
        _registry[name] = cls
        return cls
    return decorator


def get_kyc_provider(name: str | None = None) -> BaseKYCProvider:
    """Return an instantiated KYC provider. Name defaults to settings.KYC_PROVIDER."""
    if name is None:
        from django.conf import settings
        name = getattr(settings, 'KYC_PROVIDER', 'stub')
    if name not in _registry:
        raise ValueError(f"KYC provider '{name}' not registered. Available: {list(_registry)}")
    return _registry[name]()


def list_providers() -> list[str]:
    return list(_registry.keys())
