"""Shared, domain-agnostic library code (NOT a Django app).

Holds the cross-cutting primitives every domain app builds on:
  - recovery.BaseRecoveryManager : the reconciliation contract
  - dtos.BaseDTO                  : pydantic config for boundary DTOs
  - idempotency                   : deterministic idempotency-key helpers

Nothing here imports domain models — it is safe to import from any layer.
"""
