from typing import Type

from .base import BasePSP

_registry: dict[str, Type[BasePSP]] = {}


def register(name: str):
    """Class decorator: @psp_registry.register('stripe')"""
    def decorator(cls: Type[BasePSP]):
        _registry[name] = cls
        return cls
    return decorator


def get_psp(name: str | None = None) -> BasePSP:
    """Return an instantiated PSP. Name defaults to settings.PSP_PROVIDER."""
    if name is None:
        from django.conf import settings
        name = getattr(settings, 'PSP_PROVIDER', 'stub')
    if name not in _registry:
        raise ValueError(f"PSP '{name}' not registered. Available: {list(_registry)}")
    return _registry[name]()


def list_providers() -> list[str]:
    return list(_registry.keys())
