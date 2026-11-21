"""revenue Celery tasks."""
from celery import shared_task

from . import services


@shared_task(name='apps.revenue.tasks.close_days')
def close_days() -> int:
    """Hourly (idempotent): share out every completed day not yet closed."""
    return services.close_days()
