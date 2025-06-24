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

from ..models import Consigne, ManifestEntry, PDFDocument, Shipper, Vessel
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
    Service class to analyze PDF pages via OpenAI GPT with batching
    """

    def __init__(self, model: str = "gpt-3.5-turbo"):
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
        mode: str = 'text'
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
            # Construction du PDF réduit
            pdf_bytes = self.pdf_manager.create_pdf_subset(pdf_record, min(pages), max(pages))
            return self.parse_pdf_file(pdf_bytes)
        
        # mode 'text'
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
        Envoie un prompt contenant du texte à l'API et parse la réponse JSON.
        """
        prompt = (
            "Lis le contenu suivant (texte et tableaux) et retourne en JSON un ou plusieurs objets "
            "avec les champs : Name (texte, nom du navire), Flag (code pays du navire), "
            "Produits (texte, liste des produits séparés par des virgules), "
            "Volume (nombre, en m3), Poids (nombre, en kg), DATE (date au format YYYY-MM-DD), "
            "Page (nombre, le numéro de page). "
            "Si plusieurs éléments sont détectés, renvoie une liste JSON. "
            "Contenu à analyser:\n" + text
        )
        
        messages = [
            {"role": "system", "content": "Tu es un expert en analyse de documents de manifeste maritime. Réponds uniquement avec du JSON valide."},
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
        Envoie un fichier PDF binaire à l'API pour extraction directe.
        Note: Cette méthode utilise l'API Files d'OpenAI qui peut ne pas être disponible
        dans toutes les versions. Fallback vers l'extraction de texte.
        """
        try:
            # Fallback: extraire le texte du PDF et l'analyser
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmpf:
                tmpf.write(pdf_bytes)
                tmp_path = tmpf.name
            
            try:
                reader = PdfReader(tmp_path)
                text_content = ""
                for i, page in enumerate(reader.pages):
                    text_content += f"--- Page {i+1} ---\n{page.extract_text()}\n"
                
                return self.parse_text(text_content)
            finally:
                try:
                    os.remove(tmp_path)
                except:
                    pass
                    
        except Exception as e:
            return {"error": f"PDF processing error: {str(e)}"}

    def save_ai_results_to_database(self, pdf_record: PDFDocument, ai_results: List[dict]) -> Dict[str, int]:
        """
        Sauvegarde les résultats de l'IA dans la base de données
        """
        stats = {
            'vessels_created': 0,
            'vessels_found': 0,
            'entries_created': 0,
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
        Sauvegarde une entrée unique dans la base de données
        """
        try:
            # Extraire les données
            vessel_name = data.get('Name', '').strip()
            vessel_flag = data.get('Flag', '').strip()
            produits = data.get('Produits', '').strip()
            poids = data.get('Poids')
            volume = data.get('Volume')
            date_str = data.get('DATE', '')
            page = data.get('Page', 1)
            
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
            
            # Créer l'entrée de manifeste
            manifest_entry = ManifestEntry.objects.create(
                vessel=vessel,
                produits=produits,
                poids=poids,
                volume=volume,
                date=entry_date,
                page=page,
                pdf_document=pdf_record
            )
            
            stats['entries_created'] += 1
            print(f"Created manifest entry: {manifest_entry}")
            
        except Exception as e:
            stats['errors'] += 1
            print(f"Error saving entry: {e}")
            print(f"Data: {data}")

    def process_pdf_document(self, pdf_record: PDFDocument) -> Dict:
        """
        Traite complètement un document PDF avec l'IA
        """
        try:
            # Marquer comme en cours de traitement
            pdf_record.processing_status = 'processing'
            pdf_record.save()
            
            # Analyser le PDF
            results = self.analyze_pdf_pages(
                pdf_record=pdf_record,
                start_page=pdf_record.start_page,
                end_page=pdf_record.end_page,
                batch_size=3,
                mode='pdf'
            )
            
            # Sauvegarder les résultats bruts
            pdf_record.ai_results = results
            
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
