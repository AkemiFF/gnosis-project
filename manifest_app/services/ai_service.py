import io
import json
import os
import tempfile
from datetime import datetime
from typing import Dict, List, Optional, Union

import openai
from django.conf import settings
from openai import OpenAI
from PyPDF2 import PdfReader, PdfWriter

from ..models import (Category, Consigne, Container, ContainerContent,
                      ManifestEntry, PDFDocument, Shipper, Vessel)
from .pdf_manager import PDFManager


def _format_table(table: List[List[str]]) -> str:
    """
    Convert a list of rows (first row headers) into a markdown-like table string.
    """
    if not table:
        return ""
    try:
        headers = table[0]
        rows = table[1:]
        # build markdown table
        md = "| " + " | ".join(headers) + " |\n"
        md += "| " + " | ".join(['---'] * len(headers)) + " |\n"
        for row in rows:
            md += "| " + " | ".join(str(cell) if cell is not None else "" for cell in row) + " |\n"
        return md
    except Exception:
        # In case of error, return a plain text version of the table
        return "\n".join(["\t".join(str(cell) if cell is not None else "" for cell in row) for row in table])

class AIService:
    """
    Service class to analyze PDF pages via OpenAI GPT with batching and container extraction
    """

    def __init__(self, model: str = "gpt-4o"):
        api_key = getattr(settings, 'OPENAI_API_KEY', os.getenv('OPENAI_API_KEY'))
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in settings or environment variables")
        
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.pdf_manager = PDFManager()

    def analyze_pdf_pages(
        self,
        pdf_record: PDFDocument,
        start_page: Optional[int] = None,
        end_page: Optional[int] = None,
        batch_size: int = 3,
        mode: str = 'pdf'
    ) -> List[Union[dict, List[dict]]]:
        """
        Analyse un intervalle de pages, en découpant en lots de batch_size.
        mode='text' (texte formaté) ou 'pdf' (fichier PDF).
        """
        # Détermination de la plage
        total = self.pdf_manager.get_page_count(pdf_record)
        sp = start_page or 1
        ep = end_page or total
        
        if sp < 1 or ep > total or sp > ep:
            raise ValueError(f"Invalid page range: {sp} to {ep} (total {total})")
        
        pages = list(range(sp, ep + 1))

        # Générer les batches
        batches = [pages[i:i + batch_size] for i in range(0, len(pages), batch_size)]
        results = []
        
        for batch in batches:
            batch_result = self._process_batch(batch, pdf_record, mode)
            results.append(batch_result)
        
        return results

    def _process_batch(
        self,
        pages: List[int],
        pdf_record: PDFDocument,
        mode: str
    ) -> Union[dict, List[dict]]:
        """
        Traite un seul lot de pages selon le mode.
        """
        print(f"Processing pages: {pages}")
        
        if mode == 'pdf':
            # Construction du PDF réduit et envoi direct à l'IA
            pdf_bytes = self.pdf_manager.create_pdf_subset(pdf_record, min(pages), max(pages))
            return self.parse_pdf_file(pdf_bytes)
        
        # mode 'text' - fallback
        segments = []
        for num in pages:
            struct = self.pdf_manager.extract_structured(pdf_record, num)
            text = self.pdf_manager.extract_page_text(pdf_record, num)
            seg = f"--- Page {num} ---\n{text or ''}\n"
            
            for tbl in struct.get("tables", []):
                md = _format_table(tbl)
                if md:
                    seg += f"\nTableau:\n{md}\n"
            segments.append(seg)
        
        full_content = "\n".join(segments)
        return self.parse_text(full_content)

    def parse_text(self, text: str) -> Union[dict, List[dict]]:
        """
        Envoie un prompt contenant du texte à l'API et parse la réponse JSON avec extraction des containers.
        """
        prompt = (
            "Lis le contenu suivant (texte et tableaux de manifeste maritime) et retourne en JSON un ou plusieurs objets "
            "avec les champs suivants :\n\n"
            "POUR LES ENTRÉES DE MANIFESTE :\n"
            "- Name (texte, nom du navire)\n"
            "- Flag (code pays du navire)\n"
            "- Produits (texte, liste des produits séparés par des virgules)\n"
            "- Volume (nombre, en m3)\n"
            "- Poids (nombre, en kg)\n"
            "- DATE (date au format YYYY-MM-DD)\n"
            "- Page (nombre, le numéro de page)\n"
            "- Shipper (nom de l'expéditeur)\n"
            "- Consigne (nom du consignataire)\n\n"
            "POUR LES CONTAINERS :\n"
            "- Containers (liste d'objets avec les champs suivants) :\n"
            "  * numero (numéro du container, ex: MSKU1234567)\n"
            "  * type_container (type, ex: 20GP, 40GP, 40HC, 20RF, etc.)\n"
            "  * poids_brut (poids brut en kg)\n"
            "  * poids_net (poids net en kg)\n"
            "  * poids_tare (tare en kg)\n"
            "  * volume (volume en m³)\n"
            "  * longueur (longueur en mètres)\n"
            "  * largeur (largeur en mètres)\n"
            "  * hauteur (hauteur en mètres)\n"
            "  * notify_party (celui qui doit être informé à l'arrivée de la marchandise)\n"
            "  * statut (loaded, empty, damaged, maintenance, unknown)\n"
            "  * port_chargement (port de chargement)\n"
            "  * port_dechargement (port de déchargement)\n"
            "  * contents (liste des contenus du container avec) :\n"
            "    - produit (nom du produit)\n"
            "    - description (description détaillée)\n"
            "    - quantite (quantité)\n"
            "    - unite (unité de mesure)\n"
            "    - poids (poids en kg)\n"
            "    - volume (volume en m³)\n"
            "    - valeur (valeur monétaire)\n"
            "    - devise (devise)\n"
            "    - code_hs (code HS si disponible)\n"
            "    - pays_origine (pays d'origine)\n\n"
            "    - categories (liste de chaînes) : \n"
    "               Pour chaque contenu, l’IA doit choisir UNE OU PLUSIEURS catégories parmi CE LISTING EXACT :\n"
    "               Produits alimentaires / denrées alimentaires : Riz, Sucre, Farine, Légumineuses, Huile de cuisson, Produits en conserve, Épices, Boissons  \n"
    "               Matériaux de construction : Ciment, Plâtre, Sable, Tuiles, Marbre, Fer  \n"
    "               Emballages et contenants : Sacs vides, Fûts, Cartons, Palettes  \n"
    "               Produits chimiques et industriels : Peintures, Détergents, Lubrifiants, Résines, Engrais  \n"
    "               Textiles et vêtements : T-shirts, Jeans, Uniformes, Vêtements de seconde main  \n"
    "               Équipements et pièces détachées : Équipements électroniques, Pièces mécaniques, Générateurs, Panneaux solaires  \n"
    "               Véhicules et pièces automobiles : Pneus, Batteries, Motos, Pièces de rechange  \n"
    "               Articles ménagers : Meubles, Appareils électroménagers, Matelas, Literie  \n"
    "               Papeterie et fournitures de bureau : Cahiers, Stylos, Imprimantes, Cartouches d’encre  \n"
    "               Médicaments et produits médicaux : Médicaments, Équipements de soin, Gants, Masques  \n"
            "IMPORTANT :\n"
            "- Extrait TOUS les containers trouvés avec leurs numéros complets\n"
            "- Inclut TOUTES les informations de poids (brut, net, tare)\n"
            "- Extrait les dimensions si disponibles\n"
            "- Identifie le contenu de chaque container\n"
            "- Si plusieurs éléments sont détectés, renvoie une liste JSON\n"
            "- Utilise null pour les valeurs manquantes\n\n"
            "- Une content dois avoir au moins un produit (nom du produit) \n\n"
            "Contenu à analyser:\n" + text
        )
        
        messages = [
            {"role": "system", "content": "Tu es un expert en analyse de documents de manifeste maritime et de containers. Réponds uniquement avec du JSON valide. Extrait TOUTES les informations des containers avec précision."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0
            )
            full_response = response.choices[0].message.content.strip()
            
            # Nettoyer la réponse si elle contient des balises markdown
            clean_response = full_response
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            
            return json.loads(clean_response)
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            return {"error": "Invalid JSON response", "raw": full_response}
        except Exception as e:
            print(f"API error: {e}")
            return {"error": f"API error: {str(e)}"}

    def parse_pdf_file(self, pdf_bytes: bytes) -> Union[dict, List[dict]]:
        """
        Envoie un fichier PDF binaire directement à l'API OpenAI pour extraction.
        Utilise l'API Vision pour analyser le PDF comme image.
        """
        try:
            # Créer un fichier temporaire pour le PDF
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmpf:
                tmpf.write(pdf_bytes)
                tmp_path = tmpf.name
            
            try:
                # Extraire le texte du PDF pour l'analyse
                reader = PdfReader(tmp_path)
                text_content = ""
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text()
                    text_content += f"--- Page {i+1} ---\n{page_text}\n\n"
                
                # Si on a du texte, l'analyser directement
                if text_content.strip():
                    return self.parse_text(text_content)
                else:
                    return {"error": "No text content found in PDF"}
                    
            finally:
                try:
                    os.remove(tmp_path)
                except:
                    pass
                    
        except Exception as e:
            return {"error": f"PDF processing error: {str(e)}"}

    def save_ai_results_to_database(self, pdf_record: PDFDocument, ai_results: List[dict]) -> Dict[str, int]:
        """
        Sauvegarde les résultats de l'IA dans la base de données avec support des containers
        """
        stats = {
            'vessels_created': 0,
            'vessels_found': 0,
            'entries_created': 0,
            'containers_created': 0,
            'container_contents_created': 0,
            'shippers_created': 0,
            'consignes_created': 0,
            'errors': 0
        }
        
        for result in ai_results:
            if isinstance(result, list):
                # Si le résultat est une liste, traiter chaque élément
                for item in result:
                    self._save_single_entry(item, pdf_record, stats)
            elif isinstance(result, dict) and 'error' not in result:
                # Si c'est un dictionnaire sans erreur, le traiter
                self._save_single_entry(result, pdf_record, stats)
            else:
                stats['errors'] += 1
                print(f"Error in AI result: {result}")
        
        return stats

    def _save_single_entry(self, data: dict, pdf_record: PDFDocument, stats: Dict[str, int]):
        """
        Sauvegarde une entrée unique dans la base de données avec containers
        """
        try:
            print("single entry data : ", data)
            safe = lambda value: (value or '').strip()
            vessel_name = safe(data.get('Name'))
            vessel_flag = safe(data.get('Flag'))
            produits = safe(data.get('Produits'))
            poids = data.get('Poids')
            volume = data.get('Volume')
            date_str = safe(data.get('DATE'))
            page = data.get('Page', 1)
            shipper_name = safe(data.get('Shipper'))
            consigne_name = safe(data.get('Consigne'))
            containers_data = data.get('Containers') or []
            print("vessel_name :", vessel_name)
            if not vessel_name:
                stats['errors'] += 1
                return
            
            # Créer ou récupérer le navire
            vessel, created = Vessel.objects.get_or_create(
                name=vessel_name,
                defaults={'flag': vessel_flag}
            )
            
            if created:
                stats['vessels_created'] += 1
            else:
                stats['vessels_found'] += 1
                # Mettre à jour le pavillon si nécessaire
                if vessel_flag and not vessel.flag:
                    vessel.flag = vessel_flag
                    vessel.save()
            
            # Créer ou récupérer shipper
            shipper = None
            if shipper_name:
                shipper, created = Shipper.objects.get_or_create(
                    name=shipper_name,
                    defaults={'adress': ''}
                )
                if created:
                    stats['shippers_created'] += 1
            
            # Créer ou récupérer consigne
            consigne = None
            if consigne_name:
                consigne, created = Consigne.objects.get_or_create(
                    name=consigne_name,
                    defaults={'adress': ''}
                )
                if created:
                    stats['consignes_created'] += 1
            
            # Parser la date
            entry_date = None
            if date_str:
                try:
                    # Essayer différents formats de date
                    for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d']:
                        try:
                            entry_date = datetime.strptime(date_str, fmt).date()
                            break
                        except ValueError:
                            continue
                except:
                    pass
            
            if not entry_date:
                entry_date = pdf_record.date_ajout.date()
            
            # Convertir poids et volume
            try:
                poids = float(poids) if poids else None
            except (ValueError, TypeError):
                poids = None
            
            try:
                volume = float(volume) if volume else None
            except (ValueError, TypeError):
                volume = None
            
            # Traiter les containers d'abord
            created_containers = []
            for container_data in containers_data:
                container = self._create_container(container_data, vessel, shipper, consigne, pdf_record, page, stats)
                if container:
                    created_containers.append(container)
            
            # Créer l'entrée de manifeste
            # Si on a des containers, créer une entrée pour chaque container
            if created_containers:
                for container in created_containers:
                    manifest_entry = ManifestEntry.objects.create(
                        vessel=vessel,
                        container=container,
                        shipper=shipper,
                        consigne=consigne,
                        produits=produits,
                        poids=poids,
                        volume=volume,
                        date=entry_date,
                        page=page,
                        pdf_document=pdf_record
                    )
                    stats['entries_created'] += 1
            else:
                # Créer une entrée de manifeste sans container
                manifest_entry = ManifestEntry.objects.create(
                    vessel=vessel,
                    shipper=shipper,
                    consigne=consigne,
                    produits=produits,
                    poids=poids,
                    volume=volume,
                    date=entry_date,
                    page=page,
                    pdf_document=pdf_record
                )
                stats['entries_created'] += 1
            
            print(f"Created manifest entries for vessel: {vessel_name}")
            
        except Exception as e:
            stats['errors'] += 1
            print(f"Error saving entry: {e}")
            print(f"Data: {data}")

    def _create_container(self, container_data: dict, vessel, shipper, consigne, pdf_record, page, stats: Dict[str, int]):
        """
        Crée un container avec ses contenus
        """
        try:
            raw_numero = container_data.get('numero')
            if raw_numero is None:
                return None
            numero = str(raw_numero).strip()
            if not numero:
                return None

            
            # Vérifier si le container existe déjà
            existing_container = Container.objects.filter(numero=numero).first()
            if existing_container:
                print(f"Container {numero} already exists, skipping creation")
                return existing_container
            
            # Convertir les valeurs numériques de manière sécurisée
            def safe_decimal(value):
                if value is None or value == '':
                    return None
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return None
            raw_type = container_data.get('type_container')
            type_container = str(raw_type).strip() if raw_type is not None else 'OTHER'
            if type_container not in dict(Container.CONTAINER_TYPES):
                type_container = 'OTHER'

            # Créer le container
            container = Container.objects.create(
                numero=numero,
                type_container=type_container,
                poids_brut=safe_decimal(container_data.get('poids_brut')),
                poids_net=safe_decimal(container_data.get('poids_net')),
                poids_tare=safe_decimal(container_data.get('poids_tare')),
                volume=safe_decimal(container_data.get('volume')),
                longueur=safe_decimal(container_data.get('longueur')),
                largeur=safe_decimal(container_data.get('largeur')),
                hauteur=safe_decimal(container_data.get('hauteur')),
                statut=container_data.get('statut', 'loaded').lower(),
                vessel=vessel,
                shipper=shipper,
                consigne=consigne,
                port_chargement=container_data.get('port_chargement', ''),
                port_dechargement=container_data.get('port_dechargement', ''),
                pdf_document=pdf_record,
                page=page
            )
            
            stats['containers_created'] += 1
            print(f"Created container: {container.numero}")
            
            # Créer les contenus du container
            contents_data = container_data.get('contents', [])
            for content_data in contents_data:
                self._create_container_content(container, content_data, stats)
            
            return container
            
        except Exception as e:
            stats['errors'] += 1
            print(f"Error creating container: {e}")
            return None

    def _create_container_content(self, container: Container, content_data: dict, stats: Dict[str, int]):
        """
        Crée le contenu d'un container
        """
        try:
            produit = content_data.get('produit', '').strip()
            if not produit:
                return
            
            def safe_decimal(value):
                if value is None or value == '':
                    return None
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return None
            
            cc = ContainerContent.objects.create(
                container=container,
                produit=produit,
                description=content_data.get('description', ''),
                quantite=safe_decimal(content_data.get('quantite')),
                unite=content_data.get('unite', ''),
                poids=safe_decimal(content_data.get('poids')),
                volume=safe_decimal(content_data.get('volume')),
                valeur=safe_decimal(content_data.get('valeur')),
                devise=content_data.get('devise', ''),
                code_hs=content_data.get('code_hs', ''),
                pays_origine=content_data.get('pays_origine', '')
            )
            # —> Traitement des catégories fournies par l’IA
            
            for cat_name in content_data.get('categories', []):
                # On récupère ou crée la catégorie (sans parent, car l’IA ne renvoie que le nom)
                
                cat_obj, _ = Category.objects.get_or_create(name=cat_name)
                cc.categories.add(cat_obj)
    
            stats['container_contents_created'] += 1
            print(f"Created container content: {produit} for container {container.numero}")
            
        except Exception as e:
            stats['errors'] += 1
            print(f"Error creating container content: {e}")

    def process_pdf_document(self, pdf_record: PDFDocument) -> Dict:
        """
        Traite complètement un document PDF avec l'IA en envoyant directement le PDF
        """
        try:
            # Marquer comme en cours de traitement
            pdf_record.processing_status = 'processing'
            pdf_record.save()
            
            # Analyser le PDF en mode direct (envoi du PDF à l'IA)
            results = self.analyze_pdf_pages(
                pdf_record=pdf_record,
                start_page=pdf_record.start_page,
                end_page=pdf_record.end_page,
                batch_size=3,
                mode='pdf'  # Mode PDF direct
            )
            
            # Sauvegarder les résultats bruts
            pdf_record.ai_results = results
            print(results)
            # Sauvegarder dans la base de données
            stats = self.save_ai_results_to_database(pdf_record, results)
            
            # Marquer comme traité
            pdf_record.processed = True
            pdf_record.processing_status = 'completed'
            pdf_record.save()
            
            return {
                'success': True,
                'stats': stats,
                'results': results
            }
            
        except Exception as e:
            # Marquer comme erreur
            pdf_record.processing_status = 'error'
            pdf_record.save()
            
            return {
                'success': False,
                'error': str(e)
            }
