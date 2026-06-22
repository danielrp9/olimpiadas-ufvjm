from django import forms
from django.contrib.auth import get_user_model
from .models import Atleta, Modalidade

User = get_user_model()

class RegisterForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('email', 'nome_completo')

class AtletaForm(forms.ModelForm):
    class Meta:
        model = Atleta
        fields = ['nome_completo', 'cpf', 'email', 'matricula', 'curso', 'campus', 'genero']
        widgets = {
            'nome_completo': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'cpf': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500', 'placeholder': '000.000.000-00'}),
            'email': forms.EmailInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'matricula': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'curso': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'campus': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'genero': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'}),
        }
from .models import Jogo

class DelegationModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.nome_delegacao or 'Sem Nome'} (Responsável: {obj.nome_completo})"

class JogoForm(forms.ModelForm):
    time_a = DelegationModelChoiceField(
        queryset=User.objects.none(),
        label="Time A",
        widget=forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 transition shadow-sm bg-white'})
    )
    time_b = DelegationModelChoiceField(
        queryset=User.objects.none(),
        label="Time B",
        widget=forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 transition shadow-sm bg-white'})
    )

    class Meta:
        model = Jogo
        fields = ['modalidade', 'data_jogo', 'horario_jogo', 'time_a', 'time_b', 'local', 'finalizado']
        widgets = {
            'modalidade': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 transition shadow-sm bg-white'}),
            'data_jogo': forms.DateInput(attrs={'type': 'date', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 transition shadow-sm'}),
            'horario_jogo': forms.TimeInput(attrs={'type': 'time', 'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 transition shadow-sm'}),
            'local': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 transition shadow-sm'}),
            'finalizado': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-blue-600 focus:ring-blue-500/20 w-5 h-5'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reps = User.objects.filter(role='REPRESENTANTE', status_delegacao='deferido').order_by('nome_delegacao', 'email')
        self.fields['time_a'].queryset = reps
        self.fields['time_b'].queryset = reps
