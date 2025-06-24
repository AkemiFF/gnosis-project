# pdf_manifest/celery.py

import os

from celery import Celery

# Définir le settings module de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manifest_project.settings')

app = Celery('manifest_project')

# Charger config depuis les settings de Django
app.config_from_object('django.conf:settings', namespace='CELERY')

# Découvrir les tâches dans tous les apps Django
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
