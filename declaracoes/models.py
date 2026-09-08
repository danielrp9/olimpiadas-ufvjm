from django.db import models
from django.conf import settings


class MembroComissao(models.Model):
    """
    Membro da Comissão Organizadora das Olimpíadas.
    Permite emissão individual de declarações de participação como Organizador/Comissão.
    """
    nome_completo = models.CharField(max_length=255, verbose_name="Nome Completo")
    matricula = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        verbose_name="Matrícula / SIAPE",
        help_text="Número de matrícula ou SIAPE institucional"
    )
    cargo = models.CharField(
        max_length=100, 
        default="Organizador", 
        verbose_name="Papel / Cargo",
        help_text="Ex: Organizador, Coordenador de Modalidade, Apoio Técnico"
    )
    email = models.EmailField(blank=True, null=True, verbose_name="E-mail")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='declaracoes_comissao',
        verbose_name="Usuário Vinculado"
    )
    ativo = models.BooleanField(default=True, verbose_name="Ativo?")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="Cadastrado em")

    class Meta:
        verbose_name = "Membro da Comissão"
        verbose_name_plural = "Membros da Comissão"
        ordering = ['nome_completo']

    def __str__(self):
        mat = f" (Matrícula: {self.matricula})" if self.matricula else ""
        return f"{self.nome_completo}{mat} - {self.cargo}"


class HistoricoEmissao(models.Model):
    """
    Registro histórico de lotes de declarações gerados.
    """
    TIPO_CHOICES = [
        ('atleta', 'Atletas'),
        ('comissao', 'Comissão Organizadora'),
    ]
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, verbose_name="Tipo de Declaração")
    total_documentos = models.PositiveIntegerField(default=0, verbose_name="Total de Documentos")
    carga_horaria = models.PositiveIntegerField(verbose_name="Carga Horária (horas)")
    periodo = models.CharField(max_length=255, verbose_name="Período")
    cidade_data = models.CharField(max_length=255, verbose_name="Cidade e Data")
    solicitado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Solicitado Por"
    )
    data_emissao = models.DateTimeField(auto_now_add=True, verbose_name="Data de Emissão")

    class Meta:
        verbose_name = "Histórico de Emissão"
        verbose_name_plural = "Históricos de Emissões"
        ordering = ['-data_emissao']

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.total_documentos} docs em {self.data_emissao.strftime('%d/%m/%Y %H:%M')}"
