import json
import mimetypes
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.db.models.functions import TruncDay, TruncMonth
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import PDFUploadForm, UserCreateForm
from .models import *
from .models import PDFDocument
from .services.ai_service import AIService
from .services.chatbot_service import ChatbotService
from .services.pdf_manager import PDFManager
from .tasks import process_pdf_ai_task


@login_required
def view_pdf(request, pdf_id):
    """Afficher un PDF dans le navigateur"""
    pdf_doc = get_object_or_404(PDFDocument, id=pdf_id)
    
    try:
        # Ouvrir le fichier PDF
        with open(pdf_doc.file.path, 'rb') as pdf_file:
            response = HttpResponse(pdf_file.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{pdf_doc.nom}.pdf"'
            return response
    except FileNotFoundError:
        raise Http404("Le fichier PDF n'a pas été trouvé.")
    
@login_required
def delete_user(request, user_id):
    """Supprimer un utilisateur"""
    if not request.user.is_superuser:
        messages.error(request, 'Vous n\'avez pas les permissions pour supprimer des utilisateurs.')
        return redirect('utilisateurs')
    
    user_to_delete = get_object_or_404(User, id=user_id)
    
    # Empêcher la suppression de son propre compte
    if user_to_delete == request.user:
        messages.error(request, 'Vous ne pouvez pas supprimer votre propre compte.')
        return redirect('utilisateurs')
    
    if request.method == 'POST':
        username = user_to_delete.username
        user_to_delete.delete()
        messages.success(request, f'Utilisateur "{username}" supprimé avec succès.')
        return redirect('utilisateurs')
    
    return render(request, 'manifest_app/confirm_delete_user.html', {
        'user_to_delete': user_to_delete
    })
    
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
def create_user(request):
    """Créer un nouvel utilisateur"""
    if not request.user.is_superuser:
        messages.error(request, 'Vous n\'avez pas les permissions pour créer des utilisateurs.')
        return redirect('utilisateurs')
    
    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Utilisateur "{user.username}" créé avec succès!')
            return redirect('utilisateurs')
    else:
        form = UserCreateForm()
    
    return render(request, 'manifest_app/create_user.html', {'form': form})
@login_required
def home(request):
    # Statistiques générales
    total_documents = PDFDocument.objects.count()
    processed_documents = PDFDocument.objects.filter(processed=True).count()
    pending_documents = PDFDocument.objects.filter(processing_status='pending').count()
    error_documents = PDFDocument.objects.filter(processing_status='error').count()
    
    total_vessels = Vessel.objects.count()
    total_voyages = Voyage.objects.count() # Keep this line as per original, but new charts won't use it
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
    
    # FIXED: Données pour les graphiques - Utiliser les dates réelles des données
    # Trouver la plage de dates réelle des données
    date_range = ManifestEntry.objects.aggregate(
        min_date=Min('date'),
        max_date=Max('date')
    )
    
    # Si on a des données, utiliser les 6 derniers mois à partir de la date max
    # Sinon, utiliser les 6 derniers mois à partir d'aujourd'hui
    if date_range['max_date']:
        end_date = date_range['max_date']
        start_date = end_date - timedelta(days=180)  # 6 mois environ
    else:
        end_date = now().date()
        start_date = end_date - timedelta(days=180)
    
    # MODIFIED: Catégories principales par mois au lieu des entrées par mois
    # Trouver la plage de dates réelle des ContainerContent
    content_date_range = ContainerContent.objects.aggregate(
        min_date=Min('container__created_at'),
        max_date=Max('container__created_at')
    )

    # Si on a des données, utiliser les 6 derniers mois à partir de la date max
    if content_date_range['max_date']:
        content_end_date = content_date_range['max_date']
        content_start_date = content_end_date - timedelta(days=180)  # 6 mois environ
    else:
        content_end_date = now()
        content_start_date = content_end_date - timedelta(days=180)

    # Récupérer les catégories principales (sans parent) avec leurs contenus par mois
    main_categories = Category.objects.filter(parent__isnull=True)

    # Créer les données pour le graphique des catégories par mois
    monthly_categories_data = []
    for category in main_categories:
        # Compter les ContainerContent liés à cette catégorie principale par mois
        monthly_data = ContainerContent.objects.filter(
            categories=category,
            container__created_at__gte=content_start_date,
            container__created_at__lte=content_end_date
        ).annotate(
            month=TruncMonth('container__created_at')
        ).values('month').annotate(
            count=Count('id')
        ).order_by('month')
        
        # Convertir en format JSON serializable
        category_monthly_data = []
        for entry in monthly_data:
            category_monthly_data.append({
                'month': entry['month'].strftime('%Y-%m-01') if entry['month'] else None,
                'count': entry['count']
            })
        
        if category_monthly_data:  # Seulement ajouter si il y a des données
            monthly_categories_data.append({
                'category_name': category.name,
                'data': category_monthly_data
            })
    
    # Documents traités par jour - FIXED: Utiliser les 7 derniers jours à partir de la date max des documents
    doc_date_range = PDFDocument.objects.aggregate(
        min_date=Min('date_ajout'),
        max_date=Max('date_ajout')
    )
    
    if doc_date_range['max_date']:
        doc_end_date = doc_date_range['max_date'].date()
        doc_start_date = doc_end_date - timedelta(days=7)
    else:
        doc_end_date = now().date()
        doc_start_date = doc_end_date - timedelta(days=7)
    
    daily_processing_raw = PDFDocument.objects.filter(
        date_ajout__date__gte=doc_start_date,
        date_ajout__date__lte=doc_end_date,
        processed=True
        ).annotate(
            day=TruncDay('date_ajout')
        ).values(
            'day'
        ).annotate(
            count=Count('id')
        ).order_by('day')

    # Convert datetime objects to strings for JSON serialization
    daily_processing = []
    for entry in daily_processing_raw:
        daily_processing.append({
            'day': entry['day'].strftime('%Y-%m-%d') if entry['day'] else None,
            'count': entry['count']
        })

    # NEW: Documents par statut pour graphique Doughnut
    document_status_data = [
        {'status': 'Traités', 'count': processed_documents},
        {'status': 'En attente', 'count': pending_documents},
        {'status': 'Erreurs', 'count': error_documents},
    ]

    # NEW: Top 5 types de conteneurs pour graphique Bar
    top_container_types = Container.objects.values('type_container').annotate(
        count=Count('id')
    ).order_by('-count')[:5]

    # NEW: Poids total des cargaisons par mois - FIXED: Utiliser la même plage de dates
    monthly_weight_raw = ManifestEntry.objects.filter(
        date__gte=start_date,
        date__lte=end_date,
        poids__isnull=False
    ).annotate(
        month=TruncMonth('date')
    ).values(
        'month'
    ).annotate(
        total_weight=Sum('poids')
    ).order_by('month')
    
    # Convert datetime objects to strings for JSON serialization
    monthly_weight_data = []
    for entry in monthly_weight_raw:
        monthly_weight_data.append({
            'month': entry['month'].strftime('%Y-%m-01') if entry['month'] else None,
            'total_weight': float(entry['total_weight']) if entry['total_weight'] else 0
        })
    
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
        
        # Données pour graphiques - FIXED: Now using real date ranges
        'monthly_categories_data': monthly_categories_data,
        'daily_processing': daily_processing,
        'document_status_data': document_status_data,
        'top_container_types': list(top_container_types),
        'monthly_weight_data': monthly_weight_data,
        
        # Pourcentages
        'processing_percentage': round((processed_documents / total_documents * 100) if total_documents > 0 else 0, 1),
        'ai_extraction_percentage': round((ai_extracted_entries / total_entries * 100) if total_entries > 0 else 0, 1),
        
        # ADDED: Debug info for date ranges
        'debug_date_range': {
            'manifest_start': start_date.strftime('%Y-%m-%d') if start_date else None,
            'manifest_end': end_date.strftime('%Y-%m-%d') if end_date else None,
            'doc_start': doc_start_date.strftime('%Y-%m-%d') if doc_start_date else None,
            'doc_end': doc_end_date.strftime('%Y-%m-%d') if doc_end_date else None,
            'content_start': content_start_date.strftime('%Y-%m-%d') if content_start_date else None,
            'content_end': content_end_date.strftime('%Y-%m-%d') if content_end_date else None,
        }
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
    
    recent_products = ManifestEntry.objects.select_related('vessel', 'shipper').order_by('-date')[:10]
    
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
def consignes(request):
    search_query = request.GET.get('search', '')
    consignes_list = Consigne.objects.all()
    
    if search_query:
        consignes_list = consignes_list.filter(
            Q(name__icontains=search_query) |
            Q(address__icontains=search_query) |
            Q(city__icontains=search_query)
        )
    
    consignes_list = consignes_list.annotate(
        container_count=Count('container'),
        entry_count=Count('manifestentry')
    ).order_by('name')
    
    paginator = Paginator(consignes_list, 20)
    page_number = request.GET.get('page')
    consignes = paginator.get_page(page_number)
    
    context = {
        'consignes': consignes,
        'search_query': search_query,
    }
    
    return render(request, 'manifest_app/consignes.html', context)


@login_required
def containers(request):
    search_query = request.GET.get('search', '')
    type_filter = request.GET.get('type', '')
    status_filter = request.GET.get('status', '')
    vessel_filter = request.GET.get('vessel', '')
    
    containers_list = Container.objects.select_related('vessel', 'shipper', 'consigne')
    
    if search_query:
        containers_list = containers_list.filter(
            Q(numero__icontains=search_query) |
            Q(vessel__name__icontains=search_query) |
            Q(shipper__name__icontains=search_query) |
            Q(consigne__name__icontains=search_query)
        )
    
    if type_filter:
        containers_list = containers_list.filter(type_container=type_filter)
    
    if status_filter:
        containers_list = containers_list.filter(statut=status_filter)
    
    if vessel_filter:
        containers_list = containers_list.filter(vessel_id=vessel_filter)
    
    containers_list = containers_list.annotate(
        content_count=Count('containerContent')
    ).order_by('-id')
    
    # Pour les filtres
    container_types = Container.CONTAINER_TYPES
    container_statuses = Container.STATUS_CHOICES
    vessels = Vessel.objects.all().order_by('name')
    
    paginator = Paginator(containers_list, 20)
    page_number = request.GET.get('page')
    containers = paginator.get_page(page_number)
    
    context = {
        'containers': containers,
        'search_query': search_query,
        'type_filter': type_filter,
        'status_filter': status_filter,
        'vessel_filter': vessel_filter,
        'container_types': container_types,
        'container_statuses': container_statuses,
        'vessels': vessels,
    }
    
    return render(request, 'manifest_app/containers.html', context)

@login_required
def container_detail(request, container_id):
    container = get_object_or_404(Container, id=container_id)
    
    # Contenu du container
    contents = ContainerContent.objects.filter(container=container)
    
    # Statistiques du contenu
    content_stats = {
        'total_items': contents.count(),
        'total_weight': contents.aggregate(Sum('poids'))['poids__sum'] or 0,
        'total_volume': contents.aggregate(Sum('volume'))['volume__sum'] or 0,
        'total_value': contents.aggregate(Sum('valeur'))['valeur__sum'] or 0,
    }
    
    context = {
        'container': container,
        'contents': contents,
        'content_stats': content_stats,
    }
    
    return render(request, 'manifest_app/container_detail.html', context)
@login_required
def donnees(request):
    search_query = request.GET.get('search', '')
    entries = ManifestEntry.objects.select_related('vessel').all()
    
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
    users = User.objects.order_by('id')  # Explicitly order the queryset
    paginator = Paginator(users, 10)
    paginator = Paginator(users, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
    }
    return render(request, 'manifest_app/utilisateurs.html', context)

@login_required
def vessels(request):
    """Liste des navires avec recherche et filtres"""
    search_query = request.GET.get('search', '')
    flag_filter = request.GET.get('flag', '')
    sort_by = request.GET.get('sort', 'entries_count')
    
    vessels = Vessel.objects.annotate(
        entries_count=Count('manifestentry'),
        total_weight=Sum('manifestentry__poids'),
        total_volume=Sum('manifestentry__volume'),
        last_activity=Count('manifestentry__date')
    )
    
    # Filtres
    if search_query:
        vessels = vessels.filter(
            Q(name__icontains=search_query) |
            Q(flag__icontains=search_query)
        )
    
    if flag_filter:
        vessels = vessels.filter(flag__icontains=flag_filter)
    
    # Tri
    if sort_by == 'name':
        vessels = vessels.order_by('name')
    elif sort_by == 'flag':
        vessels = vessels.order_by('flag', 'name')
    elif sort_by == 'date':
        vessels = vessels.order_by('-created_at')
    else:  # entries_count par défaut
        vessels = vessels.order_by('-entries_count', 'name')
    
    # Pagination
    paginator = Paginator(vessels, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistiques pour la page
    total_vessels = Vessel.objects.count()
    total_entries = ManifestEntry.objects.count()
    countries = Vessel.objects.values_list('flag', flat=True).distinct().order_by('flag')
    
    # Top pays par nombre de navires
    top_countries = Vessel.objects.values('flag').annotate(
        vessel_count=Count('id')
    ).order_by('-vessel_count')[:5]
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'flag_filter': flag_filter,
        'sort_by': sort_by,
        'total_vessels': total_vessels,
        'total_entries': total_entries,
        'countries': countries,
        'top_countries': top_countries,
    }
    
    return render(request, 'manifest_app/vessels.html', context)

@login_required
def vessel_detail(request, vessel_id):
    """Détail d'un navire"""
    vessel = get_object_or_404(Vessel, id=vessel_id)
    
    # Entrées de manifeste pour ce navire
    entries = ManifestEntry.objects.filter(vessel=vessel).select_related('pdf_document').order_by('-date')
    
    # Statistiques
    stats = entries.aggregate(
        total_entries=Count('id'),
        total_weight=Sum('poids'),
        total_volume=Sum('volume'),
        avg_weight=Avg('poids'),
        avg_volume=Avg('volume')
    )
    
    # Voyages
    voyages = Voyage.objects.filter(vessel=vessel).order_by('-date_depart')[:10]
    
    # Produits les plus transportés
    top_products = entries.values('produits').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # Pagination des entrées
    paginator = Paginator(entries, 20)
    page_number = request.GET.get('page')
    entries_page = paginator.get_page(page_number)
    
    context = {
        'vessel': vessel,
        'stats': stats,
        'voyages': voyages,
        'top_products': top_products,
        'entries_page': entries_page,
    }
    
    return render(request, 'manifest_app/vessel_detail.html', context)
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
def process_pdf_ai_2(request, pdf_id):
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
@require_POST
def process_pdf_ai(request, pdf_id):
    """
    Lance le traitement IA d'un document PDF de façon asynchrone via Celery
    """
    pdf_doc = get_object_or_404(PDFDocument, id=pdf_id)
    
    if pdf_doc.processing_status == 'processing':
        return JsonResponse({
            'success': False,
            'error': 'Le document est déjà en cours de traitement'
        })

    if not hasattr(settings, 'OPENAI_API_KEY') or not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == 'your-openai-api-key-here':
        return JsonResponse({
            'success': False,
            'error': 'Clé API OpenAI non configurée. Veuillez configurer OPENAI_API_KEY dans settings.py'
        })

    # Marquer le document comme en traitement
    pdf_doc.processing_status = 'processing'
    pdf_doc.save()

    # Lancer la tâche asynchrone
    process_pdf_ai_task.delay(pdf_doc.id)

    return JsonResponse({
        'success': True,
        'message': 'Le traitement du document a été lancé. Vous recevrez une notification une fois terminé.'
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
