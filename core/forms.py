from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Atleta, Equipe, Modalidade, SolicitacaoInclusao

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        fields = UserCreationForm.Meta.fields + ('email',)

class AtletaForm(forms.ModelForm):
    class Meta:
        model = Atleta
        fields = ['nome_completo', 'cpf', 'email', 'matricula', 'curso', 'campus']
        widgets = {
            'nome_completo': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'cpf': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500', 'placeholder': '000.000.000-00'}),
            'email': forms.EmailInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'matricula': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'curso': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'campus': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'}),
        }

class EquipeForm(forms.ModelForm):
    class Meta:
        model = Equipe
        fields = ['nome_equipe', 'link_comprovante', 'atletas']
        widgets = {
            'nome_equipe': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'}),
            'link_comprovante': forms.URLInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500', 'placeholder': 'https://drive.google.com/...'}),
            'atletas': forms.CheckboxSelectMultiple(attrs={'class': 'grid grid-cols-1 md:grid-cols-2 gap-2'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.modalidade = kwargs.pop('modalidade', None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields['atletas'].queryset = Atleta.objects.filter(cadastrado_por=self.user)
        if self.user and self.modalidade:
            nome_sugerido = f"{self.modalidade.nome.replace(' ', '_')}_{self.user.username.replace(' ', '_')}"
            self.fields['link_comprovante'].help_text = f"Obrigatório nomear o arquivo/pasta no seu drive como: <strong>{nome_sugerido}</strong>"

    def clean_atletas(self):
        atletas = self.cleaned_data.get('atletas')
        if self.modalidade:
            count = atletas.count()
            if count < self.modalidade.limite_minimo_jogadores:
                raise forms.ValidationError(f"Você precisa selecionar pelo menos {self.modalidade.limite_minimo_jogadores} atletas para esta modalidade.")
            if count > self.modalidade.limite_maximo_jogadores:
                raise forms.ValidationError(f"Você pode selecionar no máximo {self.modalidade.limite_maximo_jogadores} atletas para esta modalidade.")
        return atletas

class SolicitacaoInclusaoForm(forms.ModelForm):
    class Meta:
        model = SolicitacaoInclusao
        fields = ['atleta', 'link_comprovante']
        widgets = {
            'link_comprovante': forms.URLInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500', 'placeholder': 'https://drive.google.com/...'}),
            'atleta': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'}),
        }

    def __init__(self, *args, **kwargs):
        self.equipe = kwargs.pop('equipe', None)
        super().__init__(*args, **kwargs)
        if self.equipe:
            atletas_atuais = self.equipe.atletas.all()
            solicitacoes_pendentes = SolicitacaoInclusao.objects.filter(equipe=self.equipe, status='pendente').values_list('atleta_id', flat=True)
            self.fields['atleta'].queryset = Atleta.objects.filter(cadastrado_por=self.equipe.representante).exclude(id__in=atletas_atuais).exclude(id__in=solicitacoes_pendentes)
            
            nome_sugerido = f"{self.equipe.modalidade.nome.replace(' ', '_')}_{self.equipe.representante.username.replace(' ', '_')}_Adicional"
            self.fields['link_comprovante'].help_text = f"Obrigatório nomear o arquivo no drive como: <strong>{nome_sugerido}</strong>"
