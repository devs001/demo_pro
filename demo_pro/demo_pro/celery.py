import os
from celery import Celery
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'billing_project.settings')

app = Celery('billing_project')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Periodic tasks
from celery.schedules import crontab

app.conf.beat_schedule = {
    'generate-monthly-invoices': {
        'task': 'billing.tasks.generate_monthly_invoices',
        'schedule': crontab(hour=0, minute=0),  # Daily at midnight
    },
    'mark-overdue-invoices': {
        'task': 'billing.tasks.mark_overdue_invoices',
        'schedule': crontab(hour=6, minute=0),  # Daily at 6 AM
    },
}