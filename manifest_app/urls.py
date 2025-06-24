from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('statistiques/', views.statistiques, name='statistiques'),
    path('documents/', views.documents, name='documents'),
    path('documents/upload/', views.upload_pdf, name='upload_pdf'),
    path('documents/<int:pdf_id>/process/', views.process_pdf_ai, name='process_pdf_ai'),
    path('documents/<int:pdf_id>/results/', views.pdf_results, name='pdf_results'),
    path('documents/<int:pdf_id>/status/', views.pdf_status, name='pdf_status'),
    path('donnees/', views.donnees, name='donnees'),
    path('utilisateurs/', views.utilisateurs, name='utilisateurs'),
    path('vessels/', views.vessels, name='vessels'),
    path('shippers/', views.shippers, name='shippers'),
    path('consignes/', views.consignes, name='consignes'),
    path('voyages/', views.voyages, name='voyages'),
]
