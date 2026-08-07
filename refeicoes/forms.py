from django import forms
from .models import RefeicaoAgendada
from core.models import Campus
from django.utils import timezone


class RefeicaoAgendadaForm(forms.ModelForm):
    campi_liberados = forms.ModelMultipleChoiceField(
        queryset=Campus.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'rounded border-slate-300 text-blue-600 focus:ring-blue-500'}),
        label="Campi Liberados para Refeição"
    )

    class Meta:
        model = RefeicaoAgendada
        fields = ['data', 'tipo', 'campi_liberados', 'ativo']
        widgets = {
            'data': forms.DateInput(attrs={'type': 'date', 'class': 'w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition'}),
            'tipo': forms.Select(attrs={'class': 'w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-blue-600 focus:ring-blue-500 w-5 h-5'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['data'].initial = timezone.localdate()
