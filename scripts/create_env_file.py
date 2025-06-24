import os

def create_env_file():
    """
    Crée un fichier .env avec les variables d'environnement nécessaires
    """
    env_content = """# Configuration Django
DEBUG=True
SECRET_KEY=django-insecure-your-secret-key-here

# Configuration OpenAI
OPENAI_API_KEY=your-openai-api-key-here

# Configuration Base de données (optionnel)
# DATABASE_URL=sqlite:///db.sqlite3
"""
    
    env_path = '.env'
    
    if not os.path.exists(env_path):
        with open(env_path, 'w') as f:
            f.write(env_content)
        print(f"Fichier {env_path} créé avec succès!")
        print("N'oubliez pas de remplacer 'your-openai-api-key-here' par votre vraie clé API OpenAI")
    else:
        print(f"Le fichier {env_path} existe déjà")

if __name__ == '__main__':
    create_env_file()
