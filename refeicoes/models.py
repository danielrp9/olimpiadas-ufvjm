from django.db import models
from django.conf import settings
from core.models import Campus, Atleta


class RefeicaoAgendada(models.Model):
    TIPO_CHOICES = [
        ('cafe', 'Café da Manhã'),
        ('almoco', 'Almoço'),
        ('jantar', 'Jantar'),
    ]

    data = models.DateField(verbose_name="Data da Refeição")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, verbose_name="Tipo de Refeição")
    campi_liberados = models.ManyToManyField(Campus, related_name='refeicoes_liberadas', verbose_name="Campi Liberados")
    ativo = models.BooleanField(default=True, verbose_name="Ativo para Validação?")
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Refeição Agendada"
        verbose_name_plural = "Refeições Agendadas"
        unique_together = ('data', 'tipo')
        ordering = ['-data', 'tipo']

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.data.strftime('%d/%m/%Y')}"


class RegistroRefeicao(models.Model):
    refeicao = models.ForeignKey(RefeicaoAgendada, on_delete=models.CASCADE, related_name='registros', verbose_name="Refeição Agendada")
    atleta = models.ForeignKey(Atleta, on_delete=models.CASCADE, related_name='registros_refeicao', verbose_name="Atleta")
    data_retirada = models.DateTimeField(auto_now_add=True, verbose_name="Data e Hora da Retirada")
    validado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Validado por")
    observacoes = models.TextField(blank=True, null=True, verbose_name="Observações")

    class Meta:
        verbose_name = "Registro de Retirada de Refeição"
        verbose_name_plural = "Registros de Retirada de Refeição"
        unique_together = ('refeicao', 'atleta')
        ordering = ['-data_retirada']

    def __str__(self):
        return f"{self.atleta.nome_completo} - {self.refeicao} ({self.data_retirada.strftime('%H:%M:%S')})"
