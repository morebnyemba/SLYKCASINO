"""sportsbook signals — fan out odds changes to the realtime engine."""
from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from . import services
from .models import Event


@receiver(post_save, sender=Event)
def publish_odds_on_save(sender, instance: Event, **kwargs):
    """After an event is created/updated, push its prices once the row is
    committed so subscribers (open bet slips) see the latest odds."""
    transaction.on_commit(lambda: services.publish_event_odds(instance))
