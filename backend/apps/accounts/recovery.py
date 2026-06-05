"""accounts fault-tolerance.

Recovery strategy
-----------------
KYC verification is an async, provider-dependent process. A player can get
stuck in `pending` if a provider webhook/callback is lost. This manager finds
players left `pending` beyond an SLA window and re-drives verification through
the provider client.

Idempotency: re-running only re-drives players still `pending`; a player already
moved to `verified`/`unverified` is skipped. The forward-only transition rule in
services.set_kyc_status prevents regressions on repeat runs.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from common.recovery import BaseRecoveryManager

from . import services
from .models import Player

PENDING_SLA = timedelta(hours=1)


class RecoveryManager(BaseRecoveryManager):
    domain = 'accounts'

    def reconcile(self) -> None:
        cutoff = timezone.now() - PENDING_SLA
        stuck = Player.objects.filter(
            kyc_status=Player.Kyc.PENDING,
        ).filter(kyc_updated_at__lt=cutoff) | Player.objects.filter(
            kyc_status=Player.Kyc.PENDING, kyc_updated_at__isnull=True,
        )
        for player in stuck.distinct():
            self.mark_scanned()
            if self.dry_run:
                self.mark_skipped(f'would re-drive KYC for player {player.id}')
                continue
            try:
                services.run_kyc_verification(player.id)
                self.mark_repaired(f'redrove KYC for player {player.id}')
            except Exception as exc:  # noqa: BLE001
                self.mark_failed(f'player {player.id}: {exc!r}')
