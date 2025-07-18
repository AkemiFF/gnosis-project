# manifest_project/celery.py

import os

from celery import Celery

# 1) Définir le module settings de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manifest_project.settings')

# 2) Créer l'instance Celery avec le même nom que ton projet
app = Celery('manifest_project')

# 3) Charger la configuration Django pour Celery
app.config_from_object('django.conf:settings', namespace='CELERY')
app.conf.broker_connection_retry_on_startup = True

# 4) Découvrir automatiquement les tâches dans toutes tes apps
app.autodiscover_tasks()

# 5) Exemple de tâche de debug
@app.task(bind=True)
def debug_task(self):
    # remplace le print par un logger si tu veux
    print(f'Request: {self.request!r}')
