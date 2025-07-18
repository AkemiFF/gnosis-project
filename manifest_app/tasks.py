import logging

from celery import shared_task

from manifest_app.models import PDFDocument

from .models import PDFDocument
from .services.ai_service import AIService

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def process_pdf_ai_task(self, pdf_id):
    try:
        logger.info(f"Début du traitement du PDF id={pdf_id}")
        pdf_doc = PDFDocument.objects.get(id=pdf_id)

        # Marquer le début du traitement
        pdf_doc.processing_status = 'processing'
        pdf_doc.save()
        logger.debug(f"PDF id={pdf_id} status mis à 'processing'")

        ai_service = AIService()
        result = ai_service.process_pdf_document(pdf_doc)

        if result.get('success'):
            pdf_doc.processing_status = 'completed'
            pdf_doc.save()
            logger.info(f"PDF id={pdf_id} traité avec succès")
            return {
                'success': True,
                'stats': result.get('stats'),
            }
        else:
            pdf_doc.processing_status = 'pending'
            pdf_doc.save()
            logger.warning(f"Traitement PDF id={pdf_id} échoué : {result.get('error')}")
            return {
                'success': False,
                'error': result.get('error')
            }

    except Exception as e:
        logger.error(f"Exception lors du traitement PDF id={pdf_id} : {e}", exc_info=True)
        if 'pdf_doc' in locals():
            pdf_doc.processing_status = 'pending'
            pdf_doc.save()
        # Remonter l'erreur au worker celery (optionnel)
        raise e

