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

from ..models import ManifestEntry, PDFDocument, Vessel, Voyage


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
    
    def get_database_schema(self):
        """
        Retourne la structure de la base de données pour l'IA
        """
        schema = {
            "models": {
                "Vessel": {
                    "fields": ["id", "name", "flag", "created_at"],
                    "description": "Navires avec nom et pavillon"
                },
                "ManifestEntry": {
                    "fields": ["id", "vessel", "produits", "poids", "volume", "date", "page", "pdf_document"],
                    "description": "Entrées de manifeste avec produits, poids, volume",
                    "relations": {
                        "vessel": "Vessel",
                        "pdf_document": "PDFDocument"
                    }
                },
                "PDFDocument": {
                    "fields": ["id", "nom", "nombre_page", "date_ajout", "processed", "processing_status"],
                    "description": "Documents PDF traités"
                },
                "Voyage": {
                    "fields": ["id", "vessel", "date_depart", "date_arrive", "port_depart", "port_arrive"],
                    "description": "Voyages des navires",
                    "relations": {
                        "vessel": "Vessel"
                    }
                }
            },
            "available_imports": [
                "from django.db.models import Q, Count, Sum, Avg, Max, Min",
                "from datetime import datetime, timedelta",
                "from manifest_app.models import Vessel, ManifestEntry, PDFDocument, Voyage"
            ],
            "examples": {
                "search_vessels": "vessels = Vessel.objects.filter(name__icontains='MAERSK')",
                "count_entries": "count = ManifestEntry.objects.count()",
                "filter_by_date": "entries = ManifestEntry.objects.filter(date__gte=datetime(2024, 1, 1))",
                "group_by_country": "stats = ManifestEntry.objects.values('vessel__flag').annotate(count=Count('id'))",
                "sum_weight": "total = ManifestEntry.objects.aggregate(total_weight=Sum('poids'))"
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
        
        Exemples de patterns :
        - Recherche : Model.objects.filter(field__icontains='terme')
        - Statistiques : Model.objects.aggregate(total=Sum('field'))
        - Groupement : Model.objects.values('field').annotate(count=Count('id'))
        - Comptage : Model.objects.count()
        
        Le code sera exécuté automatiquement, assure-toi qu'il est sûr et fonctionnel.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
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
                    'len': len, 'str': str, 'int': int, 'float': float, 'bool': bool,
                    'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
                    'min': min, 'max': max, 'sum': sum, 'sorted': sorted,
                    'range': range, 'enumerate': enumerate, 'zip': zip,
                    'print': print  # Pour debug si nécessaire
                },
                'Q': Q,
                'Count': Count,
                'Sum': Sum,
                'Avg': Avg,
                'Max': Max,
                'Min': Min,
                'datetime': datetime,
                'timedelta': timedelta,
                'Vessel': Vessel,
                'ManifestEntry': ManifestEntry,
                'PDFDocument': PDFDocument,
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
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ],
                temperature=0.3,
                max_tokens=600
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
            
            print(f"Résultats de l'exécution : {execution_result['result']}")
            
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
