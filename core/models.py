from django.db import models
from django.contrib.auth.models import User

class Atleta(models.Model):
    nome_completo = models.CharField(max_length=255)
    email = models.EmailField()
    cpf = models.CharField(max_length=14, verbose_name="CPF", null=True, blank=True)
    matricula = models.CharField(max_length=50)
    curso = models.CharField(max_length=100)
    campus = models.CharField(max_length=100)
    is_egresso = models.BooleanField(default=False, verbose_name="É egresso?", help_text="Marque se o atleta for formado.")
    link_documento_egresso = models.URLField(blank=True, null=True, help_text="Link obrigatório (Drive) caso seja egresso.")
    cadastrado_por = models.ForeignKey(User, on_delete=models.CASCADE, related_name='atletas')
    em_conformidade = models.BooleanField(default=True, help_text="Define se o atleta cumpre todos os requisitos do regulamento")
    justificativa_inconformidade = models.TextField(blank=True, null=True, help_text="Motivo pelo qual o atleta não está em conformidade")
    permite_correcao = models.BooleanField(default=False, help_text="Se marcado, o representante pode enviar um novo documento")
    link_correcao = models.URLField(blank=True, null=True, help_text="Novo documento enviado pelo representante para reavaliação")

    def __str__(self):
        return self.nome_completo

    class Meta:
        verbose_name = 'Atleta'
        verbose_name_plural = 'Atletas'

class Modalidade(models.Model):
    nome = models.CharField(max_length=100)
    limite_minimo_jogadores = models.PositiveIntegerField(default=1)
    limite_maximo_jogadores = models.PositiveIntegerField(default=20)
    inscricoes_abertas = models.BooleanField(default=True)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = 'Modalidade'
        verbose_name_plural = 'Modalidades'

class Equipe(models.Model):
    STATUS_CHOICES = [
        ('pendente', 'Aguardando aprovação de inscrição'),
        ('aprovado', 'Aprovado'),
        ('rejeitado', 'Rejeitado'),
    ]
    nome_equipe = models.CharField(max_length=100)
    modalidade = models.ForeignKey(Modalidade, on_delete=models.CASCADE, related_name='equipes')
    representante = models.ForeignKey(User, on_delete=models.CASCADE, related_name='equipes_representadas')
    link_comprovante = models.URLField(help_text="Link para o documento comprobatório (Google Drive, etc)")
    atletas = models.ManyToManyField(Atleta, related_name='equipes')
    data_inscricao = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    justificativa = models.TextField(blank=True, null=True, help_text="Comentários da comissão em caso de não aprovação")

    def __str__(self):
        return f"{self.nome_equipe} - {self.modalidade.nome}"

    class Meta:
        verbose_name = 'Equipe'
        verbose_name_plural = 'Equipes'

class SolicitacaoInclusao(models.Model):
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('aprovado', 'Aprovado'),
        ('rejeitado', 'Rejeitado'),
    ]
    equipe = models.ForeignKey(Equipe, on_delete=models.CASCADE, related_name='solicitacoes')
    atleta = models.ForeignKey(Atleta, on_delete=models.CASCADE, related_name='solicitacoes')
    link_comprovante = models.URLField(help_text="Link para o documento comprobatório específico deste atleta")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    justificativa = models.TextField(blank=True, null=True)
    data_solicitacao = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Inclusão de {self.atleta.nome_completo} em {self.equipe.nome_equipe}"
