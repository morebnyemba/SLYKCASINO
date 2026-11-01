from celery import shared_task


@shared_task(name='apps.risk.tasks.sweep')
def sweep() -> dict:
    from .services import sweep as run
    return run()
