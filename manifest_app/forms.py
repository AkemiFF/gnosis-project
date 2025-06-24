from django import forms
from .models import PDFDocument

class PDFUploadForm(forms.ModelForm):
    start_page = forms.IntegerField(
        min_value=1,
        initial=1,
        help_text="Page de début pour le traitement IA"
    )
    end_page = forms.IntegerField(
        min_value=1,
        required=False,
        help_text="Page de fin (optionnel, toutes les pages si vide)"
    )
    
    class Meta:
        model = PDFDocument
        fields = ['nom', 'file', 'start_page', 'end_page']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'Nom du document'
            }),
            'file': forms.FileInput(attrs={
                'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100',
                'accept': '.pdf'
            }),
            'start_page': forms.NumberInput(attrs={
                'class': 'block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500'
            }),
            'end_page': forms.NumberInput(attrs={
                'class': 'block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500'
            }),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        start_page = cleaned_data.get('start_page')
        end_page = cleaned_data.get('end_page')
        
        if end_page and start_page and end_page < start_page:
            raise forms.ValidationError("La page de fin doit être supérieure ou égale à la page de début.")
        
        return cleaned_data
