import os
import django
import sys

# Add the project directory to the Python path
sys.path.append('/app')

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manifest_project.settings')
django.setup()

from django.contrib.auth.models import User
from manifest_app.models import Vessel, Shipper, Consigne, Voyage, ManifestEntry, PDFDocument
from datetime import date, timedelta
import random

def create_sample_data():
    print("Creating sample data...")
    
    # Create superuser if it doesn't exist
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
        print("Created admin user (username: admin, password: admin123)")
    
    # Create sample vessels
    vessels_data = [
        {'name': 'MSC OSCAR', 'flag': 'PANAMA'},
        {'name': 'EVER GIVEN', 'flag': 'PANAMA'},
        {'name': 'CMA CGM MARCO POLO', 'flag': 'FRANCE'},
        {'name': 'OOCL HONG KONG', 'flag': 'HONG KONG'},
        {'name': 'MADRID MAERSK', 'flag': 'DENMARK'},
    ]
    
    for vessel_data in vessels_data:
        vessel, created = Vessel.objects.get_or_create(**vessel_data)
        if created:
            print(f"Created vessel: {vessel.name}")
    
    # Create sample shippers
    shippers_data = [
        {'name': 'Toyota Motor Corporation', 'adresse': 'Tokyo, Japan'},
        {'name': 'Samsung Electronics', 'adresse': 'Seoul, South Korea'},
        {'name': 'Apple Inc.', 'adresse': 'Cupertino, USA'},
        {'name': 'Volkswagen Group', 'adresse': 'Wolfsburg, Germany'},
    ]
    
    for shipper_data in shippers_data:
        shipper, created = Shipper.objects.get_or_create(**shipper_data)
        if created:
            print(f"Created shipper: {shipper.name}")
    
    # Create sample consignes
    consignes_data = [
        {'name': 'Port Authority of New York', 'adresse': 'New York, USA'},
        {'name': 'Port of Rotterdam', 'adresse': 'Rotterdam, Netherlands'},
        {'name': 'Port of Singapore', 'adresse': 'Singapore'},
        {'name': 'Port of Shanghai', 'adresse': 'Shanghai, China'},
    ]
    
    for consigne_data in consignes_data:
        consigne, created = Consigne.objects.get_or_create(**consigne_data)
        if created:
            print(f"Created consigne: {consigne.name}")
    
    # Create sample voyages
    vessels = Vessel.objects.all()
    for vessel in vessels:
        for i in range(3):
            voyage_data = {
                'vessel': vessel,
                'date_depart': date.today() - timedelta(days=random.randint(30, 365)),
                'date_arrive': date.today() - timedelta(days=random.randint(1, 29)),
                'port_depart': random.choice(['Shanghai', 'Rotterdam', 'Singapore', 'Los Angeles']),
                'port_arrive': random.choice(['New York', 'Hamburg', 'Tokyo', 'Dubai']),
            }
            voyage, created = Voyage.objects.get_or_create(**voyage_data)
            if created:
                print(f"Created voyage: {voyage}")
    
    # Create sample manifest entries
    products = [
        'Automobiles Toyota Camry',
        'Electronics Samsung Galaxy',
        'Machinery Industrial Equipment',
        'Textiles Cotton Fabric',
        'Food Products Canned Goods',
        'Chemicals Pharmaceutical',
        'Steel Products Construction Materials',
        'Furniture Office Equipment',
    ]
    
    voyages = Voyage.objects.all()
    for voyage in voyages:
        for i in range(random.randint(5, 15)):
            entry_data = {
                'vessel': voyage.vessel,
                'voyage': voyage,
                'produits': random.choice(products),
                'poids': random.uniform(1000, 50000),
                'volume': random.uniform(10, 500),
                'date': voyage.date_arrive,
                'page': random.randint(1, 10),
            }
            entry, created = ManifestEntry.objects.get_or_create(**entry_data)
            if created:
                print(f"Created manifest entry: {entry}")
    
    print("Sample data creation completed!")
    print("\n=== CONFIGURATION REQUISE ===")
    print("1. Installez les dépendances: pip install -r requirements.txt")
    print("2. Configurez votre clé OpenAI dans settings.py ou comme variable d'environnement")
    print("3. Créez le dossier media: mkdir -p media/pdfs")
    print("4. Lancez les migrations: python manage.py makemigrations && python manage.py migrate")
    print("5. Connexion: admin / admin123")

if __name__ == '__main__':
    create_sample_data()
