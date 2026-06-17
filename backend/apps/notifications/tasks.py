"""notifications Celery tasks."""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from . import services


@shared_task(name='apps.notifications.tasks.notify_expiring_promos')
def notify_expiring_promos() -> int:
    """Notify players whose active promotion claims expire within 24 hours."""
    from datetime import timedelta

    from apps.promotions.models import PromotionClaim

    cutoff = timezone.now() + timedelta(hours=24)
    claims = PromotionClaim.objects.filter(
        status=PromotionClaim.Status.ACTIVE,
        promotion__ends_at__lte=cutoff,
        promotion__ends_at__gte=timezone.now(),
    ).select_related('promotion')

    count = 0
    for claim in claims:
        promo_name = claim.promotion.name if hasattr(claim.promotion, 'name') else f'Promotion #{claim.promotion_id}'
        services.notify(
            player_id=claim.player_id,
            kind='promo_expiring',
            title='Promotion expiring soon',
            body=f'Your promotion "{promo_name}" expires within 24 hours.',
        )
        count += 1
    return count
