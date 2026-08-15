from django import forms
from .models import (
    ConfiguracaoGeral, DataDisponivel, RecursoLocal,
    ParametroModalidade, RestricaoFase
)
from core.models import Modalidade


class ConfiguracaoGeralForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoGeral
        fields = [
            'nome', 'intervalo_padrao_minutos',
            'descanso_minimo_equipe_minutos', 'duracao_padrao_jogo_minutos'
        ]
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-xl focus:ring-blue-500 focus:border-blue-500 text-sm font-medium'}),
            'intervalo_padrao_minutos': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-xl focus:ring-blue-500 focus:border-blue-500 text-sm font-medium', 'min': 0}),
            'descanso_minimo_equipe_minutos': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-xl focus:ring-blue-500 focus:border-blue-500 text-sm font-medium', 'min': 0}),
            'duracao_padrao_jogo_minutos': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-xl focus:ring-blue-500 focus:border-blue-500 text-sm font-medium', 'min': 10}),
        }


class DataDisponivelForm(forms.ModelForm):
    class Meta:
        model = DataDisponivel
        fields = ['data', 'horario_inicio', 'horario_fim', 'ativo']
        widgets = {
            'data': forms.DateInput(attrs={'type': 'date', 'class': 'w-full px-4 py-2 border border-slate-300 rounded-xl focus:ring-blue-500 focus:border-blue-500 text-sm font-medium'}),
            'horario_inicio': forms.TimeInput(attrs={'type': 'time', 'class': 'w-full px-4 py-2 border border-slate-300 rounded-xl focus:ring-blue-500 focus:border-blue-500 text-sm font-medium'}),
            'horario_fim': forms.TimeInput(attrs={'type': 'time', 'class': 'w-full px-4 py-2 border border-slate-300 rounded-xl focus:ring-blue-500 focus:border-blue-500 text-sm font-medium'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-blue-600 rounded focus:ring-blue-500'}),
        }


class RecursoLocalForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['modalidades_permitidas'].queryset = Modalidade.objects.exclude(
            nome__icontains='atletismo'
        ).order_by('nome', 'genero')

    class Meta:
        model = RecursoLocal
        fields = ['nome', 'descricao', 'modalidades_permitidas', 'ordem', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-xl focus:ring-blue-500 focus:border-blue-500 text-sm font-medium', 'placeholder': 'Ex: Quadra 1 (Ginásio)'}),
            'descricao': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-xl focus:ring-blue-500 focus:border-blue-500 text-sm font-medium', 'placeholder': 'Opcional: piso sintético, iluminação...'}),
            'modalidades_permitidas': forms.CheckboxSelectMultiple(attrs={'class': 'w-4 h-4 text-emerald-600 rounded focus:ring-emerald-500 border-slate-300'}),
            'ordem': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-xl focus:ring-blue-500 focus:border-blue-500 text-sm font-medium', 'min': 1}),
            'ativo': forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-blue-600 rounded focus:ring-blue-500'}),
        }


class RestricaoFaseForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        configuracao = kwargs.pop('configuracao', None)
        super().__init__(*args, **kwargs)
        self.fields['modalidade'].queryset = Modalidade.objects.exclude(
            nome__icontains='atletismo'
        ).order_by('nome', 'genero')
        if configuracao:
            self.fields['datas_permitidas'].queryset = DataDisponivel.objects.filter(configuracao=configuracao, ativo=True).order_by('data')

    class Meta:
        model = RestricaoFase
        fields = ['fase_codigo', 'fase_nome', 'modalidade', 'datas_permitidas', 'ordem_precedencia']
        widgets = {
            'fase_codigo': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-xl focus:ring-blue-500 focus:border-blue-500 text-sm font-medium'}),
            'fase_nome': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-xl focus:ring-blue-500 focus:border-blue-500 text-sm font-medium'}),
            'modalidade': forms.Select(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-xl focus:ring-blue-500 focus:border-blue-500 text-sm font-medium'}),
            'datas_permitidas': forms.CheckboxSelectMultiple(attrs={'class': 'rounded text-blue-600 focus:ring-blue-500'}),
            'ordem_precedencia': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 border border-slate-300 rounded-xl focus:ring-blue-500 focus:border-blue-500 text-sm font-medium', 'min': 0}),
        }


class ParametroModalidadeForm(forms.ModelForm):
    class Meta:
        model = ParametroModalidade
        fields = ['duracao_minutos', 'intervalo_pos_jogo_minutos']
        widgets = {
            'duracao_minutos': forms.NumberInput(attrs={'class': 'w-24 px-3 py-1.5 border border-slate-300 rounded-lg text-sm font-medium focus:ring-blue-500 focus:border-blue-500', 'min': 5}),
            'intervalo_pos_jogo_minutos': forms.NumberInput(attrs={'class': 'w-24 px-3 py-1.5 border border-slate-300 rounded-lg text-sm font-medium focus:ring-blue-500 focus:border-blue-500', 'min': 0}),
        }
