"""revenue Celery tasks."""
from celery import shared_task

from . import services


@shared_task(name='apps.revenue.tasks.close_days')
def close_days() -> int:
    """Hourly (idempotent): share out every completed day not yet closed."""
    from . import audit
    closed = services.close_days()
    audit.ensure_weeks()       # each finished week opens for the founder's reports
    return closed
