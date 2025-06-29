from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
import json
from datetime import datetime, timedelta
from .models import Vessel, Shipper, Consigne, Voyage, PDFDocument, ManifestEntry, ChatMessage
from .forms import PDFUploadForm
from .services.ai_service import AIService
from .services.pdf_manager import PDFManager
from .services.chatbot_service import ChatbotService

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, 'Nom d\'utilisateur ou mot de passe incorrect.')
    return render(request, 'registration/login.html')

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def home(request):
    # Statistiques générales
    total_documents = PDFDocument.objects.count()
    processed_documents = PDFDocument.objects.filter(processed=True).count()
    pending_documents = PDFDocument.objects.filter(processing_status='pending').count()
    error_documents = PDFDocument.objects.filter(processing_status='error').count()
    
    total_vessels = Vessel.objects.count()
    total_voyages = Voyage.objects.count()
    total_entries = ManifestEntry.objects.count()
    
    # Statistiques des données extraites par l'IA
    ai_extracted_entries = ManifestEntry.objects.filter(pdf_document__isnull=False).count()
    total_weight = ManifestEntry.objects.filter(poids__isnull=False).aggregate(Sum('poids'))['poids__sum'] or 0
    total_volume = ManifestEntry.objects.filter(volume__isnull=False).aggregate(Sum('volume'))['volume__sum'] or 0
    
    # Documents récents
    recent_documents = PDFDocument.objects.order_by('-date_ajout')[:5]
    
    # Entrées récentes extraites par l'IA
    recent_ai_entries = ManifestEntry.objects.filter(
        pdf_document__isnull=False
    ).select_related('vessel', 'pdf_document').order_by('-id')[:10]
    
    # Statistiques par statut de traitement
    processing_stats = PDFDocument.objects.values('processing_status').annotate(
        count=Count('id')
    ).order_by('processing_status')
    
    # Top 5 des navires par nombre d'entrées
    top_vessels = ManifestEntry.objects.values('vessel__name', 'vessel__flag').annotate(
        entries_count=Count('id'),
        total_weight=Sum('poids'),
        total_volume=Sum('volume')
    ).order_by('-entries_count')[:5]
    
    # Données pour les graphiques
    # Entrées par mois (6 derniers mois)
    six_months_ago = datetime.now() - timedelta(days=180)
    monthly_entries = ManifestEntry.objects.filter(
        date__gte=six_months_ago
    ).extra(
        select={'month': "strftime('%%Y-%%m', date)"}
    ).values('month').annotate(
        count=Count('id')
    ).order_by('month')
    
    # Documents traités par jour (7 derniers jours)
    seven_days_ago = datetime.now() - timedelta(days=7)
    daily_processing = PDFDocument.objects.filter(
        date_ajout__gte=seven_days_ago,
        processed=True
    ).extra(
        select={'day': "strftime('%%Y-%%m-%%d', date_ajout)"}
    ).values('day').annotate(
        count=Count('id')
    ).order_by('day')
    
    context = {
        # Statistiques générales
        'total_documents': total_documents,
        'processed_documents': processed_documents,
        'pending_documents': pending_documents,
        'error_documents': error_documents,
        'total_vessels': total_vessels,
        'total_voyages': total_voyages,
        'total_entries': total_entries,
        'ai_extracted_entries': ai_extracted_entries,
        'total_weight': total_weight,
        'total_volume': total_volume,
        
        # Données récentes
        'recent_documents': recent_documents,
        'recent_ai_entries': recent_ai_entries,
        
        # Statistiques détaillées
        'processing_stats': processing_stats,
        'top_vessels': top_vessels,
        
        # Données pour graphiques
        'monthly_entries': list(monthly_entries),
        'daily_processing': list(daily_processing),
        
        # Pourcentages
        'processing_percentage': round((processed_documents / total_documents * 100) if total_documents > 0 else 0, 1),
        'ai_extraction_percentage': round((ai_extracted_entries / total_entries * 100) if total_entries > 0 else 0, 1),
    }
    return render(request, 'manifest_app/home.html', context)

@login_required
def statistiques(request):
    # Données pour les graphiques
    cargo_by_country = ManifestEntry.objects.values('vessel__flag').annotate(
        nombre_cargo=Count('id')
    ).order_by('-nombre_cargo')[:10]
    
    voyage_by_vessel = Voyage.objects.values('vessel__name').annotate(
        nombre_voyage=Count('id')
    ).order_by('-nombre_voyage')[:10]
    
    recent_products = ManifestEntry.objects.select_related('vessel', 'voyage').order_by('-date')[:10]
    
    # Statistiques générales
    total_vessels = Vessel.objects.count()
    total_voyages = Voyage.objects.count()
    total_entries = ManifestEntry.objects.count()
    
    context = {
        'cargo_by_country': list(cargo_by_country),
        'voyage_by_vessel': list(voyage_by_vessel),
        'recent_products': recent_products,
        'total_vessels': total_vessels,
        'total_voyages': total_voyages,
        'total_entries': total_entries,
    }
    return render(request, 'manifest_app/statistiques.html', context)

@login_required
def documents(request):
    search_query = request.GET.get('search', '')
    documents = PDFDocument.objects.all().order_by('-date_ajout')
    
    if search_query:
        documents = documents.filter(
            Q(nom__icontains=search_query) |
            Q(nom_serveur__icontains=search_query)
        )
    
    paginator = Paginator(documents, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
    }
    return render(request, 'manifest_app/documents.html', context)

@login_required
def donnees(request):
    search_query = request.GET.get('search', '')
    entries = ManifestEntry.objects.select_related('vessel', 'voyage').all()
    
    if search_query:
        entries = entries.filter(
            Q(vessel__name__icontains=search_query) |
            Q(vessel__flag__icontains=search_query) |
            Q(produits__icontains=search_query)
        )
    
    paginator = Paginator(entries, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
    }
    return render(request, 'manifest_app/donnees.html', context)

@login_required
def utilisateurs(request):
    from django.contrib.auth.models import User
    users = User.objects.all()
    paginator = Paginator(users, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
    }
    return render(request, 'manifest_app/utilisateurs.html', context)

@login_required
def vessels(request):
    vessels = Vessel.objects.all()
    paginator = Paginator(vessels, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
    }
    return render(request, 'manifest_app/vessels.html', context)

@login_required
def shippers(request):
    shippers = Shipper.objects.all()
    paginator = Paginator(shippers, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
    }
    return render(request, 'manifest_app/shippers.html', context)

@login_required
def consignes(request):
    consignes = Consigne.objects.all()
    paginator = Paginator(consignes, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
    }
    return render(request, 'manifest_app/consignes.html', context)

@login_required
def voyages(request):
    voyages = Voyage.objects.select_related('vessel').all()
    paginator = Paginator(voyages, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
    }
    return render(request, 'manifest_app/voyages.html', context)

@login_required
def upload_pdf(request):
    if request.method == 'POST':
        form = PDFUploadForm(request.POST, request.FILES)
        if form.is_valid():
            pdf_doc = form.save(commit=False)
            
            # Générer le nom serveur
            pdf_doc.nom_serveur = pdf_doc.file.name
            
            # Calculer le nombre de pages
            try:
                pdf_manager = PDFManager()
                # Sauvegarder d'abord pour avoir le fichier sur disque
                pdf_doc.save()
                pdf_doc.nombre_page = pdf_manager.get_page_count(pdf_doc)
                
                # Ajuster end_page si nécessaire
                if not pdf_doc.end_page:
                    pdf_doc.end_page = pdf_doc.nombre_page
                elif pdf_doc.end_page > pdf_doc.nombre_page:
                    pdf_doc.end_page = pdf_doc.nombre_page
                
                pdf_doc.save()
                
                messages.success(request, f'Document "{pdf_doc.nom}" uploadé avec succès!')
                return redirect('documents')
                
            except Exception as e:
                messages.error(request, f'Erreur lors du traitement du PDF: {str(e)}')
                if pdf_doc.pk:
                    pdf_doc.delete()
    else:
        form = PDFUploadForm()
    
    return render(request, 'manifest_app/upload_pdf.html', {'form': form})

@login_required
@require_POST
def process_pdf_ai(request, pdf_id):
    """
    Lance le traitement IA d'un document PDF
    """
    pdf_doc = get_object_or_404(PDFDocument, id=pdf_id)
    
    if pdf_doc.processing_status == 'processing':
        return JsonResponse({
            'success': False,
            'error': 'Le document est déjà en cours de traitement'
        })
    
    try:
        # Vérifier que la clé OpenAI est configurée
        from django.conf import settings
        if not hasattr(settings, 'OPENAI_API_KEY') or not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == 'your-openai-api-key-here':
            return JsonResponse({
                'success': False,
                'error': 'Clé API OpenAI non configurée. Veuillez configurer OPENAI_API_KEY dans settings.py'
            })
        
        ai_service = AIService()
        result = ai_service.process_pdf_document(pdf_doc)
        
        if result['success']:
            return JsonResponse({
                'success': True,
                'stats': result['stats'],
                'message': f'Document traité avec succès! {result["stats"]["entries_created"]} entrées créées.'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result['error']
            })
            
    except Exception as e:
        # Marquer le document comme erreur
        pdf_doc.processing_status = 'error'
        pdf_doc.save()
        
        return JsonResponse({
            'success': False,
            'error': f'Erreur inattendue: {str(e)}'
        })

@login_required
def pdf_results(request, pdf_id):
    """
    Affiche les résultats du traitement IA d'un PDF
    """
    pdf_doc = get_object_or_404(PDFDocument, id=pdf_id)
    
    # Récupérer les entrées de manifeste créées à partir de ce PDF
    manifest_entries = ManifestEntry.objects.filter(pdf_document=pdf_doc).select_related('vessel')
    
    # Calculer le nombre de navires uniques
    unique_vessels_count = manifest_entries.values('vessel').distinct().count()
    
    # Calculer le nombre de pages traitées
    if pdf_doc.end_page and pdf_doc.start_page:
        pages_processed = pdf_doc.end_page - pdf_doc.start_page + 1
    else:
        pages_processed = 1
    
    context = {
        'pdf_doc': pdf_doc,
        'manifest_entries': manifest_entries,
        'unique_vessels_count': unique_vessels_count,
        'pages_processed': pages_processed,
        'ai_results': pdf_doc.ai_results,
        'processing_status': pdf_doc.processing_status,
    }
    
    return render(request, 'manifest_app/pdf_results.html', context)

@login_required
def pdf_status(request, pdf_id):
    """
    API endpoint pour vérifier le statut de traitement d'un PDF
    """
    pdf_doc = get_object_or_404(PDFDocument, id=pdf_id)
    
    return JsonResponse({
        'status': pdf_doc.processing_status,
        'processed': pdf_doc.processed,
        'entries_count': ManifestEntry.objects.filter(pdf_document=pdf_doc).count()
    })

@login_required
def chatbot_view(request):
    """
    Vue principale du chatbot
    """
    # Récupérer l'historique des conversations de l'utilisateur
    chat_history = ChatMessage.objects.filter(user=request.user)[:20]
    
    # Obtenir les questions suggérées
    try:
        chatbot_service = ChatbotService()
        suggested_questions = chatbot_service.get_suggested_questions()
    except Exception as e:
        suggested_questions = [
            "Quels sont les navires les plus actifs ?",
            "Combien de documents ont été traités ?",
            "Quels produits sont les plus importés ?",
        ]
    
    context = {
        'chat_history': chat_history,
        'suggested_questions': suggested_questions,
    }
    return render(request, 'manifest_app/chatbot.html', context)

@login_required
def chatbot_advanced_view(request):
    """
    Vue pour le chatbot avancé avec génération de code
    """
    # Récupérer l'historique des conversations de l'utilisateur
    chat_history = ChatMessage.objects.filter(user=request.user)[:10]
    
    # Obtenir les questions suggérées
    try:
        chatbot_service = ChatbotService()
        suggested_questions = chatbot_service.get_suggested_questions()
    except Exception as e:
        suggested_questions = [
            "Combien de navires sont enregistrés ?",
            "Quels sont les 5 navires les plus actifs ?",
            "Quel est le poids total des cargaisons ?",
            "Quels pays ont le plus de navires ?",
        ]
    
    context = {
        'chat_history': chat_history,
        'suggested_questions': suggested_questions,
    }
    return render(request, 'manifest_app/chatbot_advanced.html', context)

@login_required
@require_POST
def chatbot_api(request):
    """
    API endpoint pour le chatbot
    """
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return JsonResponse({
                'success': False,
                'error': 'Message vide'
            })
        
        # Traiter la requête avec le service chatbot
        chatbot_service = ChatbotService()
        result = chatbot_service.process_chat_query(user_message)
        
        if result['success']:
            # Sauvegarder la conversation
            ChatMessage.objects.create(
                user=request.user,
                message=user_message,
                response=result['response'],
                intent=result.get('intent', {})
            )
            
            return JsonResponse({
                'success': True,
                'response': result['response'],
                'intent': result.get('intent', {}),
                'data': result.get('data', {})
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Erreur inconnue')
            })
    
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Format JSON invalide'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        })

@login_required
def clear_chat_history(request):
    """
    Efface l'historique de chat de l'utilisateur
    """
    if request.method == 'POST':
        ChatMessage.objects.filter(user=request.user).delete()
        messages.success(request, 'Historique de chat effacé avec succès.')
    
    return redirect('chatbot')
