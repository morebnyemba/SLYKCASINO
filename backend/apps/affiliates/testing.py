"""Test helpers for the affiliates app."""
from datetime import timedelta

from django.utils import timezone

from .models import Affiliate, Referral


def backdate_links(days: int = 30) -> None:
    """Fixtures create tickets 'settled' minutes ago right after linking the
    customer; in real life the link and the agent's approval come first. Move
    every link and activation back so those tickets count."""
    then = timezone.now() - timedelta(days=days)
    Referral.objects.update(created_at=then)
    Affiliate.objects.filter(active_since__isnull=False).update(active_since=then)
