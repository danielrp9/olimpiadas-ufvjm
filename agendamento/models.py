from django.db import models
from django.conf import settings
import datetime


class ConfiguracaoGeral(models.Model):
    """
    Configurações globais para a geração de cronograma e horários dos jogos.
    """
    nome = models.CharField(max_length=150, default="Configuração Principal")
    ativo = models.BooleanField(default=True, verbose_name="Configuração Ativa")
    intervalo_padrao_minutos = models.PositiveIntegerField(
        default=10,
        verbose_name="Intervalo padrão de transição (minutos)",
        help_text="Tempo de intervalo para troca de times/aquecimento no mesmo recurso"
    )
    descanso_minimo_equipe_minutos = models.PositiveIntegerField(
        default=60,
        verbose_name="Descanso mínimo entre jogos da mesma equipe (minutos)",
        help_text="Tempo mínimo de recuperação entre duas partidas de uma mesma delegação/equipe"
    )
    duracao_padrao_jogo_minutos = models.PositiveIntegerField(
        default=50,
        verbose_name="Duração padrão de jogo (minutos)",
        help_text="Duração estimada da partida caso a modalidade não possua duração específica"
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuração Geral de Agendamento"
        verbose_name_plural = "Configurações Gerais de Agendamento"

    def __str__(self):
        return f"{self.nome} ({'Ativa' if self.ativo else 'Inativa'})"


class DataDisponivel(models.Model):
    """
    Datas gerais disponíveis para a realização dos jogos da competição,
    com janela de horário de funcionamento.
    """
    configuracao = models.ForeignKey(ConfiguracaoGeral, on_delete=models.CASCADE, related_name='datas')
    data = models.DateField(verbose_name="Data da Competição")
    horario_inicio = models.TimeField(default=datetime.time(8, 0), verbose_name="Horário de Início")
    horario_fim = models.TimeField(default=datetime.time(22, 0), verbose_name="Horário Limite")
    ativo = models.BooleanField(default=True, verbose_name="Disponível?")

    class Meta:
        verbose_name = "Data Disponível"
        verbose_name_plural = "Datas Disponíveis"
        ordering = ['data']
        unique_together = ('configuracao', 'data')

    def __str__(self):
        return f"{self.data.strftime('%d/%m/%Y')} ({self.horario_inicio.strftime('%H:%M')} - {self.horario_fim.strftime('%H:%M')})"


class RecursoLocal(models.Model):
    """
    Recursos físicos/quadras/locais onde as partidas podem ser alocadas.
    """
    configuracao = models.ForeignKey(ConfiguracaoGeral, on_delete=models.CASCADE, related_name='recursos')
    nome = models.CharField(max_length=120, verbose_name="Nome do Local/Recurso")
    descricao = models.CharField(max_length=255, blank=True, verbose_name="Descrição/Observação")
    modalidades_permitidas = models.ManyToManyField(
        'core.Modalidade',
        blank=True,
        related_name='recursos_locais_agendamento',
        help_text="Selecione as modalidades compatíveis. Se nenhuma for selecionada, o local aceitará qualquer modalidade."
    )
    ativo = models.BooleanField(default=True, verbose_name="Ativo?")
    ordem = models.PositiveIntegerField(default=1, verbose_name="Ordem de Prioridade")

    class Meta:
        verbose_name = "Recurso / Local de Jogo"
        verbose_name_plural = "Recursos / Locais de Jogos"
        ordering = ['ordem', 'nome']

    def __str__(self):
        return self.nome


class ParametroModalidade(models.Model):
    """
    Duração e tempo de transição específicos por modalidade esportiva.
    """
    configuracao = models.ForeignKey(ConfiguracaoGeral, on_delete=models.CASCADE, related_name='parametros_modalidades')
    modalidade = models.ForeignKey('core.Modalidade', on_delete=models.CASCADE, related_name='parametros_agendamento')
    duracao_minutos = models.PositiveIntegerField(default=50, verbose_name="Duração da Partida (minutos)")
    intervalo_pos_jogo_minutos = models.PositiveIntegerField(default=10, verbose_name="Buffer/Intervalo Pós-Jogo (minutos)")

    class Meta:
        verbose_name = "Parâmetro por Modalidade"
        verbose_name_plural = "Parâmetros por Modalidade"
        unique_together = ('configuracao', 'modalidade')

    def __str__(self):
        return f"{self.modalidade.nome} ({self.duracao_minutos} min + {self.intervalo_pos_jogo_minutos} min buffer)"


class RestricaoFase(models.Model):
    """
    Restrição obrigatória de datas por fase da competição.
    Define as datas permitidas em que as partidas de determinada fase DEVEM ocorrer.
    """
    configuracao = models.ForeignKey(ConfiguracaoGeral, on_delete=models.CASCADE, related_name='restricoes_fases')
    fase_codigo = models.CharField(max_length=50, db_index=True, verbose_name="Código da Fase")
    fase_nome = models.CharField(max_length=100, blank=True, verbose_name="Nome da Fase")
    modalidade = models.ForeignKey(
        'core.Modalidade',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='restricoes_fases_agendamento',
        help_text="Opcional: vincular a uma modalidade específica. Se vazio, aplica-se a todas."
    )
    datas_permitidas = models.ManyToManyField(
        DataDisponivel,
        blank=True,
        related_name='fases_restringidas',
        verbose_name="Datas Permitidas para esta Fase",
        help_text="Se nenhuma data for selecionada, a fase poderá usar qualquer data geral da competição."
    )
    ordem_precedencia = models.PositiveIntegerField(
        default=0,
        verbose_name="Ordem Lógica de Precedência",
        help_text="Fases com ordem menor devem ocorrer antes de fases com ordem maior."
    )

    class Meta:
        verbose_name = "Restrição de Data por Fase"
        verbose_name_plural = "Restrições de Datas por Fases"
        ordering = ['ordem_precedencia', 'fase_codigo']

    def __str__(self):
        mod_str = f" [{self.modalidade.nome}]" if self.modalidade else " [Geral]"
        return f"{self.fase_nome or self.fase_codigo}{mod_str}"


class CenarioExecucao(models.Model):
    """
    Registro histórico e resultado de uma simulação ou geração de cronograma.
    """
    STATUS_CHOICES = [
        ('sucesso', 'Viável (Sucesso)'),
        ('inviavel', 'Inviável (Conflitos Detectados)'),
        ('aplicado', 'Aplicado ao Calendário Oficial'),
    ]

    configuracao = models.ForeignKey(ConfiguracaoGeral, on_delete=models.CASCADE, related_name='cenarios')
    titulo = models.CharField(max_length=150, default="Cronograma Gerado")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='sucesso')
    mensagem_diagnostico = models.TextField(blank=True, null=True, verbose_name="Diagnóstico / Erros")
    metricas = models.JSONField(default=dict, blank=True, verbose_name="Métricas da Alocação")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cenário de Agendamento"
        verbose_name_plural = "Cenários de Agendamentos"
        ordering = ['-criado_em']

    def __str__(self):
        return f"{self.titulo} - {self.get_status_display()} ({self.criado_em.strftime('%d/%m/%Y %H:%M')})"


class ItemAlocacao(models.Model):
    """
    Item individual de alocação de partida dentro de um cenário.
    """
    cenario = models.ForeignKey(CenarioExecucao, on_delete=models.CASCADE, related_name='alocacoes')
    partida_chaveamento = models.ForeignKey(
        'core.PartidaChaveamento',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alocacoes_agendador'
    )
    jogo = models.ForeignKey(
        'core.Jogo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alocacoes_agendador'
    )
    modalidade_nome = models.CharField(max_length=100)
    fase_codigo = models.CharField(max_length=50)
    fase_display = models.CharField(max_length=100)
    
    time_a_id = models.IntegerField(null=True, blank=True)
    time_a_nome = models.CharField(max_length=150, default="A definir")
    time_b_id = models.IntegerField(null=True, blank=True)
    time_b_nome = models.CharField(max_length=150, default="A definir")

    data_alocada = models.DateField(verbose_name="Data Alocada")
    horario_inicio = models.TimeField(verbose_name="Horário de Início")
    horario_fim = models.TimeField(verbose_name="Horário de Término")
    
    recurso_local = models.ForeignKey(
        RecursoLocal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alocacoes'
    )
    recurso_nome = models.CharField(max_length=120)
    status = models.CharField(max_length=20, default='alocado')

    class Meta:
        verbose_name = "Item de Alocação"
        verbose_name_plural = "Itens de Alocação"
        ordering = ['data_alocada', 'horario_inicio', 'recurso_nome']

    def __str__(self):
        return f"{self.data_alocada.strftime('%d/%m')} {self.horario_inicio.strftime('%H:%M')} [{self.recurso_nome}] {self.modalidade_nome}: {self.time_a_nome} x {self.time_b_nome}"
