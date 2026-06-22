from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.core.exceptions import ValidationError
from users.utils.cpf_validator import validate_cpf

class ComissaoWhitelist(models.Model):
    """
    Tabela de Whitelist para a Comissão Organizadora.
    Apenas e-mails cadastrados previamente nesta lista receberão o papel 'COMISSAO'.
    """
    email = models.EmailField(unique=True, verbose_name="E-mail Autorizado")
    data_adicao = models.DateTimeField(auto_now_add=True, verbose_name="Data de Adição")

    def __str__(self):
        return self.email

    class Meta:
        verbose_name = "Whitelist da Comissão"
        verbose_name_plural = "Whitelists da Comissão"


class UserManager(BaseUserManager):
    """
    Manager personalizado para o modelo User onde o e-mail é o identificador único
    para autenticação, dispensando o campo username.
    """
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("O endereço de e-mail é obrigatório.")
        email = self.normalize_email(email)
        
        # Como o login é 100% social via Google, senhas não são criadas localmente
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'COMISSAO')
        extra_fields.setdefault('perfil_completo', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser precisa ter is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser precisa ter is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Modelo de Usuário Personalizado para o Sistema de Olimpíadas.
    Autenticação puramente social (sem username e sem senha local).
    """
    username = None  # Remove o campo username padrão do Django
    email = models.EmailField(unique=True, verbose_name="E-mail")
    nome_completo = models.CharField(max_length=255, verbose_name="Nome Completo")
    foto_url = models.URLField(max_length=1000, null=True, blank=True, verbose_name="URL da Foto de Perfil")
    google_id = models.CharField(max_length=255, unique=True, null=True, blank=True, verbose_name="Google Subject ID")
    
    # RBAC (Controle de Acesso Baseado em Papéis)
    ROLE_CHOICES = [
        ('COMISSAO', 'Comissão Organizadora'),
        ('REPRESENTANTE', 'Representante de Delegação'),
    ]
    role = models.CharField(
        max_length=20, 
        choices=ROLE_CHOICES, 
        default='REPRESENTANTE', 
        verbose_name="Papel de Acesso"
    )
    
    # Campo CPF (específico de Representante, obrigatório na 2ª etapa)
    cpf = models.CharField(
        max_length=14, 
        unique=True, 
        null=True, 
        blank=True, 
        verbose_name="CPF"
    )
    
    # Informações da Delegação do Representante
    nome_delegacao = models.CharField(
        max_length=255, 
        null=True, 
        blank=True, 
        verbose_name="Nome da Delegação"
    )
    
    STATUS_DELEGACAO_CHOICES = [
        ('pendente', 'Pendente de Análise'),
        ('deferido', 'Deferido (Aprovado)'),
        ('indeferido', 'Indeferido (Recusado)'),
    ]
    status_delegacao = models.CharField(
        max_length=20,
        choices=STATUS_DELEGACAO_CHOICES,
        default='pendente',
        verbose_name="Status da Delegação"
    )
    justificativa_delegacao = models.TextField(
        blank=True,
        null=True,
        verbose_name="Justificativa da Delegação"
    )
    
    # Controle de fluxo de cadastro em duas etapas
    perfil_completo = models.BooleanField(
        default=False, 
        verbose_name="Perfil Completado?"
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # O email e a senha (se existisse) são tratados pelo Django

    def clean(self):
        super().clean()
        # Se for representante e tiver preenchido o CPF, valida
        if self.role == 'REPRESENTANTE' and self.cpf:
            # Remove formatações antes de validar
            clean_cpf = ''.join(filter(str.isdigit, self.cpf))
            if not validate_cpf(clean_cpf):
                raise ValidationError({'cpf': 'O CPF informado é inválido.'})

    def save(self, *args, **kwargs):
        self.clean()
        
        # Ajusta automaticamente o perfil_completo com base no tipo
        if self.role == 'COMISSAO':
            self.perfil_completo = True
            self.is_staff = True  # Comissão pode acessar o painel admin
        else:
            # Para representante, o perfil está completo se CPF E Nome da Delegação estiverem informados
            if self.cpf and self.nome_delegacao:
                self.perfil_completo = True
            else:
                self.perfil_completo = False
                
        super().save(*args, **kwargs)

    @property
    def is_comissao(self) -> bool:
        return self.role == 'COMISSAO'

    @property
    def is_representante(self) -> bool:
        return self.role == 'REPRESENTANTE'

    def __str__(self):
        return f"{self.nome_completo or self.email} ({self.get_role_display()})"
