from django import forms
from .models import MembroComissao
from core.models import Campus


class MembroComissaoForm(forms.ModelForm):
    class Meta:
        model = MembroComissao
        fields = ['nome_completo', 'matricula', 'cargo', 'email', 'ativo']
        widgets = {
            'nome_completo': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white',
                'placeholder': 'Ex: Daniel Rodrigues Pereira'
            }),
            'matricula': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white',
                'placeholder': 'Ex: 20212016010 ou SIAPE'
            }),
            'cargo': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white',
                'placeholder': 'Ex: Organizador'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white',
                'placeholder': 'email@ufvjm.edu.br'
            }),
            'ativo': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 border-slate-200 rounded focus:ring-blue-500/20 focus:outline-none accent-blue-600'
            }),
        }
