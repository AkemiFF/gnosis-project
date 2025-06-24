import io
import os
from typing import Dict, List, Optional
from PyPDF2 import PdfReader, PdfWriter
import fitz  # PyMuPDF for better text extraction
from django.conf import settings
from ..models import PDFDocument

class PDFManager:
    """
    Service pour gérer les fichiers PDF et l'extraction de contenu
    """
    
    def __init__(self):
        self.media_root = settings.MEDIA_ROOT
    
    def get_file_path(self, pdf_record: PDFDocument) -> str:
        """Retourne le chemin complet du fichier PDF"""
        return pdf_record.file.path
    
    def extract_page_text(self, pdf_record: PDFDocument, page_num: int) -> str:
        """Extrait le texte d'une page spécifique"""
        try:
            file_path = self.get_file_path(pdf_record)
            doc = fitz.open(file_path)
            
            if page_num < 1 or page_num > len(doc):
                return ""
            
            page = doc.load_page(page_num - 1)  # fitz uses 0-based indexing
            text = page.get_text()
            doc.close()
            return text
        except Exception as e:
            print(f"Error extracting text from page {page_num}: {e}")
            return ""
    
    def extract_structured(self, pdf_record: PDFDocument, page_num: int) -> Dict:
        """Extrait les données structurées (tableaux) d'une page"""
        try:
            file_path = self.get_file_path(pdf_record)
            doc = fitz.open(file_path)
            
            if page_num < 1 or page_num > len(doc):
                return {"tables": []}
            
            page = doc.load_page(page_num - 1)
            tables = page.find_tables()
            
            structured_data = {"tables": []}
            for table in tables:
                table_data = table.extract()
                if table_data:
                    structured_data["tables"].append(table_data)
            
            doc.close()
            return structured_data
        except Exception as e:
            print(f"Error extracting structured data from page {page_num}: {e}")
            return {"tables": []}
    
    def get_page_count(self, pdf_record: PDFDocument) -> int:
        """Retourne le nombre de pages du PDF"""
        try:
            file_path = self.get_file_path(pdf_record)
            reader = PdfReader(file_path)
            return len(reader.pages)
        except Exception as e:
            print(f"Error getting page count: {e}")
            return 0
    
    def create_pdf_subset(self, pdf_record: PDFDocument, start_page: int, end_page: int) -> bytes:
        """Crée un sous-ensemble du PDF avec les pages spécifiées"""
        try:
            file_path = self.get_file_path(pdf_record)
            reader = PdfReader(file_path)
            writer = PdfWriter()
            
            for page_num in range(start_page - 1, min(end_page, len(reader.pages))):
                writer.add_page(reader.pages[page_num])
            
            buffer = io.BytesIO()
            writer.write(buffer)
            buffer.seek(0)
            return buffer.read()
        except Exception as e:
            print(f"Error creating PDF subset: {e}")
            return b""
