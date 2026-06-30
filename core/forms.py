from django import forms
from django.contrib.auth import get_user_model
from .models import Atleta, Modalidade, Jogo

User = get_user_model()

class RegisterForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('email', 'nome_completo')

class AtletaForm(forms.ModelForm):
    class Meta:
        model = Atleta
        fields = ['nome_completo', 'cpf', 'email', 'matricula', 'curso', 'campus', 'genero', 'link_documento', 'is_egresso']
        widgets = {
            'nome_completo': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'}),
            'cpf': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white', 'placeholder': '000.000.000-00'}),
            'email': forms.EmailInput(attrs={'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'}),
            'matricula': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'}),
            'curso': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'}),
            'campus': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'}),
            'genero': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'}),
            'link_documento': forms.URLInput(attrs={
                'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white',
                'placeholder': 'https://drive.google.com/drive/folders/...'
            }),
            'is_egresso': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-blue-600 border-slate-200 rounded focus:ring-blue-500/20 focus:outline-none accent-blue-600'}),
        }

class ModalidadeForm(forms.ModelForm):
    class Meta:
        model = Modalidade
        fields = ['nome', 'genero', 'limite_minimo_jogadores', 'limite_maximo_jogadores', 'inscricoes_abertas', 'data_publicacao']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'}),
            'genero': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'}),
            'limite_minimo_jogadores': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'}),
            'limite_maximo_jogadores': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'}),
            'inscricoes_abertas': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-blue-600 border-slate-200 rounded focus:ring-blue-500/20 focus:outline-none accent-blue-600'}),
            'data_publicacao': forms.DateTimeInput(
                attrs={
                    'type': 'datetime-local',
                    'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'
                },
                format='%Y-%m-%dT%H:%M'
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.data_publicacao:
            self.initial['data_publicacao'] = self.instance.data_publicacao.strftime('%Y-%m-%dT%H:%M')

from django.db.models import Q

class DelegationModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.nome_delegacao or 'Sem Nome'} (Responsável: {obj.nome_completo})"

class JogoForm(forms.ModelForm):
    time_a = DelegationModelChoiceField(
        queryset=User.objects.none(),
        label="Time A",
        widget=forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'})
    )
    time_b = DelegationModelChoiceField(
        queryset=User.objects.none(),
        label="Time B",
        widget=forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'})
    )

    class Meta:
        model = Jogo
        fields = ['modalidade', 'data_jogo', 'horario_jogo', 'time_a', 'time_b', 'local', 'finalizado']
        widgets = {
            'modalidade': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'}),
            'data_jogo': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'}),
            'horario_jogo': forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'}),
            'local': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-blue-100 focus:border-blue-500 transition text-xs bg-slate-50/30 focus:bg-white'}),
            'finalizado': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-blue-600 border-slate-200 rounded focus:ring-blue-500/20 focus:outline-none accent-blue-600'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reps = User.objects.filter(role='REPRESENTANTE', status_delegacao='deferido').order_by('nome_delegacao', 'email')
        
        # Garante que os times da partida atual estejam no queryset de opções de edição
        if self.instance and self.instance.pk:
            additional_ids = []
            if self.instance.time_a_id:
                additional_ids.append(self.instance.time_a_id)
            if self.instance.time_b_id:
                additional_ids.append(self.instance.time_b_id)
            if additional_ids:
                reps = User.objects.filter(
                    Q(role='REPRESENTANTE', status_delegacao='deferido') | Q(id__in=additional_ids)
                ).distinct().order_by('nome_delegacao', 'email')
                
        self.fields['time_a'].queryset = reps
        self.fields['time_b'].queryset = reps

        # Define limite mínimo do calendário (evita datas passadas)
        from django.utils import timezone
        hoje = timezone.localdate()
        if self.instance and self.instance.pk and self.instance.data_jogo:
            # Se for edição, permite selecionar a data do próprio jogo (mesmo se for passada) ou hoje
            limite_data = min(self.instance.data_jogo, hoje)
        else:
            limite_data = hoje
        self.fields['data_jogo'].widget.attrs['min'] = limite_data.strftime('%Y-%m-%d')


