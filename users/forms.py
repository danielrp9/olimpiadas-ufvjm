from django import forms
from django.contrib.auth import get_user_model
from users.utils.cpf_validator import validate_cpf

User = get_user_model()

class CompleteProfileForm(forms.ModelForm):
    """
    Formulário para a segunda etapa do cadastro do Representante.
    Nesta etapa, o usuário é obrigado a fornecer um CPF válido/único e o nome da sua Delegação.
    """
    cpf = forms.CharField(
        max_length=14, 
        required=True, 
        label="CPF",
        widget=forms.TextInput(attrs={
            'placeholder': '000.000.000-00',
            'class': 'w-full px-4 py-3 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200 shadow-sm'
        })
    )

    nome_delegacao = forms.CharField(
        max_length=255,
        required=True,
        label="Nome da Delegação, Atlética ou Competidor Individual",
        widget=forms.TextInput(attrs={
            'placeholder': 'Ex: Atlética Suprema, Time de Servidores ou Competidor Individual',
            'class': 'w-full px-4 py-3 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200 shadow-sm'
        })
    )

    class Meta:
        model = User
        fields = ['cpf', 'nome_delegacao']

    def clean_cpf(self):
        cpf_raw = self.cleaned_data.get('cpf')
        
        # Remove caracteres especiais (pontos, traços e espaços)
        cpf_clean = ''.join(filter(str.isdigit, cpf_raw))
        
        # 1. Valida o algoritmo do CPF
        if not validate_cpf(cpf_clean):
            raise forms.ValidationError("O CPF informado é inválido. Por favor, verifique os dígitos.")
            
        # 2. Verifica se o CPF já está em uso por outro usuário
        # Exclui o próprio usuário atual da busca para permitir atualizações futuras, se necessário
        user_id = self.instance.pk if self.instance else None
        qs = User.objects.filter(cpf=cpf_clean)
        if user_id:
            qs = qs.exclude(pk=user_id)
            
        if qs.exists():
            raise forms.ValidationError("Este CPF já está cadastrado no sistema.")
            
        return cpf_clean
