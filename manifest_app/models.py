from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models


class Vessel(models.Model):
    name = models.CharField(max_length=200)
    flag = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class Shipper(models.Model):
    name = models.CharField(max_length=200)
    adress = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class Consigne(models.Model):
    name = models.CharField(max_length=200)
    adress = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class Voyage(models.Model):
    vessel = models.ForeignKey(Vessel, on_delete=models.CASCADE)
    date_depart = models.DateField()
    date_arrive = models.DateField()
    port_depart = models.CharField(max_length=200)
    port_arrive = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.vessel.name} - {self.date_depart}"

class PDFDocument(models.Model):
    nom = models.CharField(max_length=200)
    nom_serveur = models.CharField(max_length=200)
    nombre_page = models.IntegerField(null=True,blank=True)
    date_ajout = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='pdfs/')
    # Nouveaux champs pour l'IA
    processed = models.BooleanField(default=False)
    processing_status = models.CharField(max_length=50, default='pending')  # pending, processing, completed, error
    ai_results = models.JSONField(null=True, blank=True)
    start_page = models.IntegerField(default=1)
    end_page = models.IntegerField(null=True, blank=True)
    
    def __str__(self):
        return self.nom

class Container(models.Model):
    CONTAINER_TYPES = [
        ('20GP', '20\' General Purpose'),
        ('40GP', '40\' General Purpose'),
        ('40HC', '40\' High Cube'),
        ('20RF', '20\' Refrigerated'),
        ('40RF', '40\' Refrigerated'),
        ('20OT', '20\' Open Top'),
        ('40OT', '40\' Open Top'),
        ('20FR', '20\' Flat Rack'),
        ('40FR', '40\' Flat Rack'),
        ('20TK', '20\' Tank'),
        ('OTHER', 'Autre'),
    ]
    
    STATUS_CHOICES = [
        ('loaded', 'Chargé'),
        ('empty', 'Vide'),
        ('damaged', 'Endommagé'),
        ('repair', 'En réparation'),
        ('transit', 'En transit'),
        ('delivered', 'Livré'),
    ]
    
    numero = models.CharField(max_length=20, unique=True)
    type_container = models.CharField(max_length=10, choices=CONTAINER_TYPES, default='OTHER')
    vessel = models.ForeignKey(Vessel, on_delete=models.CASCADE, null=True, blank=True)
    shipper = models.ForeignKey(Shipper, on_delete=models.SET_NULL, null=True, blank=True)
    consigne = models.ForeignKey(Consigne, on_delete=models.SET_NULL, null=True, blank=True)
    pdf_document = models.ForeignKey(PDFDocument, on_delete=models.CASCADE)
    page = models.IntegerField(default=1)
    
    # Poids et dimensions
    poids_brut = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0'))]
    )
    poids_net = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0'))]
    )
    poids_tare = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0'))]
    )
    volume = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0'))]
    )
    longueur = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0'))]
    )
    largeur = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0'))]
    )
    hauteur = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0'))]
    )
    
    # Statut et ports
    statut = models.CharField(max_length=20, choices=STATUS_CHOICES, default='loaded')
    port_chargement = models.CharField(max_length=100, blank=True)
    port_dechargement = models.CharField(max_length=100, blank=True)
    
    # Scellés
    scelle_douane = models.CharField(max_length=50, blank=True)
    scelle_transporteur = models.CharField(max_length=50, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.numero} ({self.type_container})"
    
    class Meta:
        ordering = ['-created_at']

class ContainerContent(models.Model):
    container = models.ForeignKey(Container, on_delete=models.CASCADE, related_name='containerContent')
    produit = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    code_hs = models.CharField(max_length=20, blank=True)
    quantite = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0'))]
    )
    unite = models.CharField(max_length=20, blank=True)
    poids = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0'))]
    )
    volume = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0'))]
    )
    valeur = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0'))]
    )
    devise = models.CharField(max_length=10, blank=True, null=True)
    pays_origine = models.CharField(max_length=100, blank=True, null=True)
    marques_numeros = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.produit} - {self.container.numero}"
    
    class Meta:
        ordering = ['produit']

class ManifestEntry(models.Model):
    pdf_document = models.ForeignKey(PDFDocument, on_delete=models.CASCADE)
    vessel = models.ForeignKey(Vessel, on_delete=models.CASCADE)
    container = models.ForeignKey(Container, on_delete=models.SET_NULL, null=True, blank=True)
    shipper = models.ForeignKey(Shipper, on_delete=models.SET_NULL, null=True, blank=True)
    consigne = models.ForeignKey(Consigne, on_delete=models.SET_NULL, null=True, blank=True)
    
    numero_bl = models.CharField(max_length=50, blank=True)
    produits = models.TextField()
    quantite = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0'))]
    )
    unite = models.CharField(max_length=20, blank=True)
    poids = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0'))]
    )
    volume = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0'))]
    )
    valeur = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0'))]
    )
    devise = models.CharField(max_length=10, blank=True)
    
    port_chargement = models.CharField(max_length=100, blank=True)
    port_dechargement = models.CharField(max_length=100, blank=True)
    
    date = models.DateField()
    page = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.vessel.name} - {self.produits[:50]}"
    
    class Meta:
        ordering = ['-date', '-created_at']


class ChatMessage(models.Model):
    """
    Modèle pour stocker l'historique des conversations du chatbot
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    response = models.TextField()
    intent = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.created_at.strftime('%d/%m/%Y %H:%M')}"