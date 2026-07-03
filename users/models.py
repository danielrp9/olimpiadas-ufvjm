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
    
    # Campo para delegação compartilhada / co-delegado
    parent_delegate = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sub_delegados',
        verbose_name="Delegado Principal"
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
    
    # Comprovante de Pagamento Único
    link_comprovante_pagamento = models.URLField(
        max_length=1000, 
        null=True, 
        blank=True, 
        verbose_name="Link do Comprovante de Pagamento Único"
    )
    
    STATUS_PAGAMENTO_CHOICES = [
        ('nao_avaliado', 'Não avaliado'),
        ('deferido', 'Deferido (Aprovado)'),
        ('indeferido', 'Indeferido (Recusado)'),
    ]
    status_pagamento = models.CharField(
        max_length=20,
        choices=STATUS_PAGAMENTO_CHOICES,
        default='nao_avaliado',
        verbose_name="Status do Pagamento"
    )
    justificativa_pagamento = models.TextField(
        blank=True,
        null=True,
        verbose_name="Justificativa do Pagamento"
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
            if not self.is_superuser:
                self.is_staff = False
            
            if self.parent_delegate:
                # Se for sub-delegado, copia o status de perfil completo do pai
                self.perfil_completo = self.parent_delegate.perfil_completo
            else:
                # Para representante principal, o perfil está completo se CPF E Nome da Delegação estiverem informados
                if self.cpf and self.nome_delegacao:
                    self.perfil_completo = True
                else:
                    self.perfil_completo = False
                
        super().save(*args, **kwargs)

        # Se for delegado principal, atualiza todos os sub-delegados vinculados
        if self.role == 'REPRESENTANTE' and not self.parent_delegate:
            self.sub_delegados.all().update(perfil_completo=self.perfil_completo)

    @property
    def delegacao_ativa(self):
        if self.parent_delegate:
            return self.parent_delegate
        return self

    @property
    def is_comissao(self) -> bool:
        return self.role == 'COMISSAO'

    @property
    def is_representante(self) -> bool:
        return self.role == 'REPRESENTANTE'

    def __str__(self):
        return f"{self.nome_completo or self.email} ({self.get_role_display()})"


class MembroDelegacao(models.Model):
    """
    Tabela de membros autorizados por um delegado representante.
    Membros nesta lista poderão acessar o perfil/delegação do delegado principal.
    """
    delegado_principal = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='membros_autorizados',
        verbose_name="Delegado Principal"
    )
    email = models.EmailField(verbose_name="E-mail Autorizado")
    data_adicao = models.DateTimeField(auto_now_add=True, verbose_name="Data de Adição")

    class Meta:
        verbose_name = "Membro da Delegação"
        verbose_name_plural = "Membros da Delegação"
        unique_together = ('delegado_principal', 'email')

    def __str__(self):
        return f"{self.email} -> {self.delegado_principal.nome_delegacao or self.delegado_principal.email}"

    def save(self, *args, **kwargs):
        # Normaliza email para lowercase
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)
        
        # Sincroniza o usuário existente, se houver
        existing_user = User.objects.filter(email__iexact=self.email).first()
        if existing_user:
            existing_user.parent_delegate = self.delegado_principal
            existing_user.role = 'REPRESENTANTE'
            existing_user.perfil_completo = self.delegado_principal.perfil_completo
            existing_user.save()

    def delete(self, *args, **kwargs):
        email = self.email
        delegado_principal = self.delegado_principal
        super().delete(*args, **kwargs)
        
        # Sincroniza desvinculação se o usuário existir
        existing_user = User.objects.filter(email__iexact=email, parent_delegate=delegado_principal).first()
        if existing_user:
            existing_user.parent_delegate = None
            existing_user.save()

