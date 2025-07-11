from django.contrib import admin

from .models import *


@admin.register(Vessel)
class VesselAdmin(admin.ModelAdmin):
    list_display = ['name', 'flag', 'created_at']
    search_fields = ['name', 'flag']

@admin.register(Shipper)
class ShipperAdmin(admin.ModelAdmin):
    list_display = ['name', 'adress', 'created_at']
    search_fields = ['name']

@admin.register(Consigne)
class ConsigneAdmin(admin.ModelAdmin):
    list_display = ['name', 'adress', 'created_at']
    search_fields = ['name']

@admin.register(Voyage)
class VoyageAdmin(admin.ModelAdmin):
    list_display = ['vessel', 'date_depart', 'date_arrive', 'port_depart', 'port_arrive']
    list_filter = ['date_depart', 'vessel']

@admin.register(PDFDocument)
class PDFDocumentAdmin(admin.ModelAdmin):
    list_display = ['nom', 'nombre_page', 'date_ajout']
    search_fields = ['nom']

@admin.register(ManifestEntry)
class ManifestEntryAdmin(admin.ModelAdmin):
    list_display = ['vessel', 'date', 'poids', 'volume', 'page']
    list_filter = ['date', 'vessel']
    search_fields = ['vessel__name', 'produits']

@admin.register(Container)
class ContainerAdmin(admin.ModelAdmin):
    list_display = ['numero', 'created_at']
    search_fields = ['container_number', 'type']

@admin.register(ContainerContent)
class ContainerContentAdmin(admin.ModelAdmin):
    list_display = ['container', 'code_hs']
    list_filter = ['container']
    search_fields = ['description', 'container__container_number']
