from django.contrib.auth.models import User
from django.db import models


class Vessel(models.Model):
    name = models.CharField(max_length=200)
    flag = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class Shipper(models.Model):
    name = models.CharField(max_length=200)
    adresse = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class Consigne(models.Model):
    name = models.CharField(max_length=200)
    adresse = models.TextField()
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

class ManifestEntry(models.Model):
    vessel = models.ForeignKey(Vessel, on_delete=models.CASCADE)
    voyage = models.ForeignKey(Voyage, on_delete=models.CASCADE, null=True, blank=True)
    produits = models.TextField()
    poids = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    volume = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    date = models.DateField()
    page = models.IntegerField(default=1)
    pdf_document = models.ForeignKey(PDFDocument, on_delete=models.CASCADE, null=True, blank=True)
    
    def __str__(self):
        return f"{self.vessel.name} - {self.date}"


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