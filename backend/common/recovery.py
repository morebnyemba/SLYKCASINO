"""Reconciliation / fault-tolerance contract shared by every domain.

Each app's ``recovery.py`` defines a ``RecoveryManager`` subclassing
:class:`BaseRecoveryManager` and implementing :meth:`reconcile`. Managers are
invoked by Celery beat tasks (see each app's ``tasks.py``) on a schedule.

Idempotency is a hard requirement: :meth:`reconcile` must be safe to run any
number of times. Re-running may *find nothing to do* but must never create
duplicate side effects (ledger rows, provider calls, state transitions).

``dry_run=True`` lets a manager report what it *would* repair without mutating
anything — useful for ops dashboards and safe periodic auditing.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class RecoveryReport(BaseModel):
    """Mutable accumulator describing the outcome of a reconciliation run."""

    domain: str
    dry_run: bool = False
    scanned: int = 0
    repaired: int = 0
    skipped: int = 0
    failed: int = 0
    details: list[str] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    @property
    def ok(self) -> bool:
        return self.failed == 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BaseRecoveryManager(ABC):
    """Base for all domain reconciliation managers.

    Subclasses set :attr:`domain` and implement :meth:`reconcile`, using the
    ``mark_*`` helpers to record outcomes on the report.
    """

    domain: str = 'base'

    def __init__(self, *, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.report = RecoveryReport(domain=self.domain, dry_run=dry_run)
        self.log = logging.getLogger(f'recovery.{self.domain}')

    @abstractmethod
    def reconcile(self) -> None:
        """Detect and idempotently repair inconsistencies for this domain."""

    def run(self) -> RecoveryReport:
        """Execute one reconciliation pass and return the report."""
        self.report.started_at = _now()
        self.log.info('recovery start domain=%s dry_run=%s', self.domain, self.dry_run)
        try:
            self.reconcile()
        except Exception as exc:  # noqa: BLE001 — managers must never crash the worker
            self.report.failed += 1
            self.report.details.append(f'fatal: {exc!r}')
            self.log.exception('recovery crashed domain=%s', self.domain)
        finally:
            self.report.finished_at = _now()
        self.log.info(
            'recovery done domain=%s scanned=%s repaired=%s skipped=%s failed=%s',
            self.domain, self.report.scanned, self.report.repaired,
            self.report.skipped, self.report.failed,
        )
        return self.report

    # -- outcome helpers for subclasses ------------------------------------
    def mark_scanned(self, n: int = 1) -> None:
        self.report.scanned += n

    def mark_repaired(self, detail: str) -> None:
        self.report.repaired += 1
        self.report.details.append(detail)
        self.log.info('repaired domain=%s %s', self.domain, detail)

    def mark_skipped(self, detail: str) -> None:
        self.report.skipped += 1

    def mark_failed(self, detail: str) -> None:
        self.report.failed += 1
        self.report.details.append(f'failed: {detail}')
        self.log.warning('repair failed domain=%s %s', self.domain, detail)
