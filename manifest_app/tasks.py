from celery import shared_task

from .models import PDFDocument
from .services.ai_service import AIService


@shared_task
def process_pdf_ai_task(pdf_id):
    try:
        pdf_doc = PDFDocument.objects.get(id=pdf_id)

        # Marquer le début du traitement
        pdf_doc.processing_status = 'processing'
        pdf_doc.save()

        ai_service = AIService()
        result = ai_service.process_pdf_document(pdf_doc)

        if result['success']:
            pdf_doc.processing_status = 'completed'
            pdf_doc.save()
            return {
                'success': True,
                'stats': result['stats'],
            }
        else:
            pdf_doc.processing_status = 'pending'
            pdf_doc.save()
            return {
                'success': False,
                'error': result['error']
            }

    except Exception as e:
        if 'pdf_doc' in locals():
            pdf_doc.processing_status = 'pending'
            pdf_doc.save()
        return {
            'success': False,
            'error': str(e)
        }
