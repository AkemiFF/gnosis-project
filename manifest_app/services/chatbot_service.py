import json
import os
import sys
import traceback
from datetime import datetime, timedelta
from io import StringIO

import openai
from django.conf import settings
from django.db.models import Avg, Count, Max, Min, Q, Sum
from openai import OpenAI

from ..models import *


class ChatbotService:
    """
    Service de chatbot intelligent utilisant l'IA pour générer du code de recherche
    """
    
    def __init__(self):
        api_key = getattr(settings, 'OPENAI_API_KEY', os.getenv('OPENAI_API_KEY'))
        if not api_key or api_key == 'your-openai-api-key-here':
            raise ValueError("OPENAI_API_KEY not configured")
        
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-3.5-turbo"
        self.model_2 = "gpt-4o"

    
    def get_database_schema(self):
        """
        Retourne la structure de la base de données pour l'IA
        """
        schema = {
        "models": {
            "Category": {
                "fields": ["id", "name", "parent"],
                "description": "Catégories hiérarchiques de marchandises ou produits",
                "relations": {
                    "parent": "Category"
                }
            },
            "Vessel": {
                "fields": ["id", "name", "flag", "created_at"],
                "description": "Navires avec nom et pavillon"
            },
            "Shipper": {
                "fields": ["id", "name", "adress", "created_at"],
                "description": "Expéditeurs des marchandises"
            },
            "Consigne": {
                "fields": ["id", "name", "adress", "created_at"],
                "description": "Destinataires ou consignataires"
            },
            "Voyage": {
                "fields": ["id", "vessel", "date_depart", "date_arrive", "port_depart", "port_arrive", "created_at"],
                "description": "Voyages des navires",
                "relations": {
                    "vessel": "Vessel"
                }
            },
            "PDFDocument": {
                "fields": [
                    "id", "nom", "nom_serveur", "nombre_page", "date_ajout", "file",
                    "processed", "processing_status", "ai_results", "start_page", "end_page"
                ],
                "description": "Documents PDF analysés pour extraction IA"
            },
            "Container": {
                "fields": [
                    "id", "numero", "type_container", "vessel", "shipper", "consigne", "pdf_document", "page",
                    "notify_party", "poids_brut", "poids_net", "poids_tare", "volume",
                    "longueur", "largeur", "hauteur",
                    "statut", "port_chargement", "port_dechargement",
                    "scelle_douane", "scelle_transporteur", "created_at"
                ],
                "description": "Containers maritimes avec leurs caractéristiques",
                "relations": {
                    "vessel": "Vessel",
                    "shipper": "Shipper",
                    "consigne": "Consigne",
                    "pdf_document": "PDFDocument"
                }
            },
            "ContainerContent": {
                "fields": [
                    "id", "container", "produit", "description", "code_hs","categories", "quantite", "unite", "poids", "volume",
                    "valeur", "devise", "pays_origine", "marques_numeros"
                ],
                "description": "Contenu détaillé des containers, avec des produits liés à une ou plusieurs catégories (ManyToMany)",
                "relations": {
                    "container": "Container",
                    "categories": "Category"
                }
            },
            
            "ChatMessage": {
                "fields": ["id", "user", "message", "response", "intent", "created_at"],
                "description": "Historique des messages utilisateurs et réponses du chatbot",
                "relations": {
                    "user": "auth.User"
                }
            }
        },
        "available_imports": [
            "from django.db.models import Q, Count, Sum, Avg, Max, Min",
            "from datetime import datetime, timedelta",
            "from manifest_app.models import Category, Vessel, Shipper, Consigne, Voyage, PDFDocument, Container, ContainerContent, ManifestEntry, ChatMessage"
        ],
        "examples": {
            "search_vessels": "vessels = Vessel.objects.filter(name__icontains='MAERSK')",
            "count_entries": "count = ManifestEntry.objects.count()",
            "filter_by_date": "recent = ManifestEntry.objects.filter(date__gte=datetime(2025, 1, 1))",
            "group_by_flag": "stats = Vessel.objects.values('flag').annotate(nb=Count('id'))",
            "sum_container_weight": "totaux = Container.objects.aggregate(total_brut=Sum('poids_brut'))",
            "get_container_contents": "contents = ContainerContent.objects.filter(container__numero='MSKU1234567')",
            "find_subcategories": "subs = Category.objects.filter(parent__name='Electronics')",
            "recent_chat": "msgs = ChatMessage.objects.filter(created_at__date=datetime.today())"
        }
    }

        return schema
    
    def generate_search_code(self, user_query):
        """
        Génère du code Python pour effectuer la recherche basée sur la requête utilisateur
        """
        schema = self.get_database_schema()
        
        system_prompt = f"""
        Tu es un expert en Django ORM et en analyse de données de manifestes maritimes.
        
        Structure de la base de données :
        {json.dumps(schema, indent=2, ensure_ascii=False)}
        
        Génère du code Python utilisant Django ORM pour répondre à la requête de l'utilisateur.
        
        RÈGLES IMPORTANTES :
        1. Utilise uniquement les modèles Django fournis (Vessel, ManifestEntry, PDFDocument, Voyage)
        2. Retourne UNIQUEMENT le code Python, pas d'explication
        3. Le code doit stocker le résultat dans une variable appelée 'result'
        4. Utilise les imports déjà disponibles
        5. Gère les cas où aucun résultat n'est trouvé
        6. Pour les listes, limite à 20 résultats maximum avec [:20]
        7. Convertis les QuerySets en listes avec list() si nécessaire
        8. Pour les agrégations, utilise .values() pour obtenir des dictionnaires
        9. Toujours faire comme "Model.objects.filter(field__icontains='terme')" pour les recherches
        
        Exemples de patterns :
        - Recherche : Model.objects.filter(field__icontains='terme')
        - Statistiques : Model.objects.aggregate(total=Sum('field'))
        - Groupement : Model.objects.values('field').annotate(count=Count('id'))
        - Comptage : Model.objects.count()
        
        Le code sera exécuté automatiquement, assure-toi qu'il est sûr et fonctionnel.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_2,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Requête utilisateur: {user_query}"}
                ],
                temperature=0.1,
                max_tokens=500
            )
            
            code = response.choices[0].message.content.strip()
            
            # Nettoyer le code des balises markdown si présentes
            if code.startswith(r"```python"):
                code = code[9:]
            if code.startswith(r"```"):
                code = code[3:]
            if code.endswith(r"```"):
                code = code[:-3]
            print(code)
            return code.strip()
        except Exception as e:
            print(f"Error generating search code: {e}")
            return None
    
    def execute_search_code(self, code):
        """
        Exécute le code généré de manière sécurisée et retourne le résultat
        """
        try:
            # Imports autorisés

            allowed_globals = {
                '__builtins__': {
                    # fonctions Python de base
                    'len': len, 'str': str, 'int': int, 'float': float, 'bool': bool,
                    'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
                    'min': min, 'max': max, 'sum': sum, 'sorted': sorted,
                    'range': range, 'enumerate': enumerate, 'zip': zip,
                    'print': print,
                    # autoriser import
                    '__import__': __import__,
                },
                '__name__': '__main__',  
                '__package__': None, 
                # Django ORM
                'Q': Q,
                'Count': Count, 'Sum': Sum, 'Avg': Avg, 'Max': Max, 'Min': Min,
                # standard lib
                'datetime': datetime, 'timedelta': timedelta,
                'json': json,
                'os': os,
                # vos modèles
                'Vessel': Vessel,
                'Shipper': Shipper,
                'Consigne': Consigne,
                'PDFDocument': PDFDocument,
                'Category': Category,
                'Container': Container,
                'ContainerContent': ContainerContent,
                'ManifestEntry': ManifestEntry,
                'Voyage': Voyage,
            }

            
            # Variables locales pour stocker le résultat
            local_vars = {}
            print("Code : ",code)
            # Capturer stdout pour les éventuels prints
            old_stdout = sys.stdout
            sys.stdout = captured_output = StringIO()
            
            try:
                # Exécuter le code
                exec(code, allowed_globals, local_vars)
                
                # Récupérer le résultat
                result = local_vars.get('result', None)
                
                # Convertir les QuerySets en données sérialisables
                if hasattr(result, '__iter__') and not isinstance(result, (str, dict)):
                    try:
                        # Si c'est un QuerySet avec .values(), le convertir en liste
                        if hasattr(result, 'values'):
                            result = list(result.values())
                        else:
                            result = list(result)
                    except:
                        result = str(result)
                
                return {
                    'success': True,
                    'result': result,
                    'output': captured_output.getvalue()
                }
            
            finally:
                sys.stdout = old_stdout
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }
    
    def format_results_with_ai(self, user_query, search_results):
        """
        Utilise l'IA pour formater les résultats de recherche en réponse naturelle
        """
        system_prompt = """
        Tu es un assistant expert en analyse de données de manifestes maritimes.
        
        Formate les résultats de recherche en une réponse naturelle et informative en français.
        
        RÈGLES :
        1. Réponds de manière conversationnelle et claire
        2. Utilise les données pour donner des informations précises
        3. Si les résultats sont vides, explique pourquoi
        4. Ajoute des insights ou observations pertinentes
        5. Utilise des chiffres et statistiques quand c'est pertinent
        6. Propose des actions de suivi si approprié
        7. Garde un ton professionnel mais accessible
        8. Répond en format markdown (MD)
        
        Format de réponse préféré :
        - Réponse directe à la question
        - Détails pertinents
        - Chiffres clés
        - Observations ou insights
        """
        
        context = f"""
        Question de l'utilisateur : {user_query}
        
        Résultats de la recherche :
        {json.dumps(search_results, indent=2, default=str, ensure_ascii=False)}
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_2,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ],
                temperature=0.3,
                # max_tokens=5000
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error formatting results: {e}")
            return f"J'ai trouvé des résultats mais je n'ai pas pu les formater correctement. Résultats bruts : {search_results}"
    
    def process_chat_query(self, user_query):
        """
        Traite une requête de chat complète avec le nouveau système
        """
        try:
            # 1. Générer le code de recherche
            print(f"Génération du code pour : {user_query}")
            search_code = self.generate_search_code(user_query)
            
            if not search_code:
                return {
                    "success": False,
                    "response": "Désolé, je n'ai pas pu générer le code de recherche approprié.",
                    "error": "Code generation failed"
                }
            
            print(f"Code généré :\n{search_code}")
            
            # 2. Exécuter le code
            execution_result = self.execute_search_code(search_code)
          
            if not execution_result['success']:
                return {
                    "success": False,
                    "response": f"Erreur lors de l'exécution de la recherche : {execution_result['error']}",
                    "error": execution_result['error'],
                    "code": search_code
                }
            
            # print(f"Résultats de l'exécution : {execution_result['result']}")
            
            # 3. Formater la réponse avec l'IA
            formatted_response = self.format_results_with_ai(user_query, execution_result['result'])
            
            return {
                "success": True,
                "response": formatted_response,
                "raw_results": execution_result['result'],
                "generated_code": search_code,
                "execution_output": execution_result.get('output', '')
            }
        
        except Exception as e:
            print(f"Error processing chat query: {e}")
            return {
                "success": False,
                "response": "Désolé, une erreur s'est produite lors du traitement de votre demande.",
                "error": str(e)
            }
    def get_suggested_questions(self):
        """
        Retourne des questions suggérées
        """
        suggestions = [
            "Quels sont les catégories définies ?",
            "De quels catégories sont les marchandises les plus importé ?",
            "Quelles sont les principales catégories de marchandises ?",      
            "Quelle est la valeur totale des marchandises importées par catégorie ?",
            "Quel est le volume moyen par type de produit ?",
            "Combien d'articles différents ont été enregistrés ?",
            "Combien de navires sont enregistrés ?",
            "Quels sont les 5 navires les plus actifs ?",
            "Quel est le poids total des cargaisons ?",
            "Quels pays ont le plus de navires ?",
            "Combien de documents ont été traités ?",
            "Quels sont les produits les plus importés ?",
            "Statistiques des voyages par mois",
            "Navires avec pavillon français"
        ]

        return suggestions
