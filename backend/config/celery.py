"""Celery application for the SLYK backend.

Workers run domain recovery tasks; beat schedules periodic reconciliation
(see CELERY_BEAT_SCHEDULE in settings). Each app exposes its tasks in
``apps.<domain>.tasks`` and they are auto-discovered below.
"""
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('slyk')

# Pull CELERY_* settings from Django config.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Discover apps.<domain>.tasks modules.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):  # pragma: no cover - smoke task
    print(f'Request: {self.request!r}')
