from django.db import models
from django.conf import settings

class Campus(models.Model):
    nome = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = 'Campus'
        verbose_name_plural = 'Campi'


class Atleta(models.Model):
    """
    Modelo representativo de um Atleta da delegação acadêmica.
    Possui restrição de gênero para adequação a modalidades masculina/feminina.
    """
    GENERO_CHOICES = [
        ('M', 'Masculino'),
        ('F', 'Feminino'),
        ('N', 'Não-binário'),
    ]
    TIPO_ATLETA_CHOICES = [
        ('estudante', 'Estudante'),
        ('servidor', 'Servidor/Técnico'),
    ]
    nome_completo = models.CharField(max_length=255)
    email = models.EmailField()
    cpf = models.CharField(max_length=14, verbose_name="CPF", null=True, blank=True)
    matricula = models.CharField(max_length=50, verbose_name="Matrícula/SIAPE")
    curso = models.CharField(max_length=100, verbose_name="Curso (estudante)/Lotação (servidor)")
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, null=True, blank=True)
    genero = models.CharField(max_length=1, choices=GENERO_CHOICES, default='M', verbose_name="Gênero")
    tipo_atleta = models.CharField(max_length=20, choices=TIPO_ATLETA_CHOICES, default='estudante', verbose_name="Tipo de Atleta")
    link_documento = models.URLField(blank=True, null=True, help_text="Link para o documento de identificação (RG, CNH, etc.)")
    is_egresso = models.BooleanField(default=False, verbose_name="É egresso?", help_text="Marque se o atleta for formado.")
    link_documento_egresso = models.URLField(blank=True, null=True, help_text="Link obrigatório (Drive) caso seja egresso.")
    cadastrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='atletas')
    STATUS_AVALIACAO_CHOICES = [
        ('nao_avaliado', 'Não avaliado'),
        ('deferido', 'Deferido'),
        ('indeferido', 'Indeferido'),
    ]
    status_avaliacao = models.CharField(
        max_length=20,
        choices=STATUS_AVALIACAO_CHOICES,
        default='nao_avaliado',
        verbose_name="Status da Avaliação"
    )
    em_conformidade = models.BooleanField(default=False, help_text="Define se o atleta cumpre todos os requisitos do regulamento")
    justificativa_inconformidade = models.TextField(blank=True, null=True, help_text="Motivo pelo qual o atleta não está em conformidade")
    permite_correcao = models.BooleanField(default=False, help_text="Se marcado, o representante pode enviar um novo documento")
    link_correcao = models.URLField(blank=True, null=True, help_text="Novo documento enviado pelo representante para reavaliação")


    def __str__(self):
        return f"{self.nome_completo} ({self.get_genero_display()})"

    class Meta:
        verbose_name = 'Atleta'
        verbose_name_plural = 'Atletas'


class Modalidade(models.Model):
    """
    Representa as modalidades esportivas ofertadas na Olimpíada.
    """
    GENERO_MODALIDADE_CHOICES = [
        ('M', 'Masculino'),
        ('F', 'Feminino'),
        ('X', 'Misto'),
    ]
    nome = models.CharField(max_length=100)
    genero = models.CharField(max_length=1, choices=GENERO_MODALIDADE_CHOICES, default='M', verbose_name="Gênero da Categoria")
    limite_minimo_jogadores = models.PositiveIntegerField(default=1)
    limite_maximo_jogadores = models.PositiveIntegerField(default=20)
    inscricoes_abertas = models.BooleanField(default=True)
    data_publicacao = models.DateTimeField(blank=True, null=True, verbose_name="Data/Hora de Publicação (Agendamento)", help_text="Se preenchido, a modalidade só ficará pública para inscrições a partir desta data/hora.")

    def __str__(self):
        return f"{self.nome} ({self.get_genero_display()})"

    class Meta:
        verbose_name = 'Modalidade'
        verbose_name_plural = 'Modalidades'


class Jogo(models.Model):
    """
    Representa uma partida oficial agendada pela Comissão.
    Vincula as duas delegações autorizadas a participar.
    """
    modalidade = models.ForeignKey(Modalidade, on_delete=models.CASCADE, related_name='jogos')
    data_jogo = models.DateField(verbose_name="Data do Jogo")
    horario_jogo = models.TimeField(verbose_name="Horário do Jogo", blank=True, null=True)
    time_a = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='jogos_time_a', verbose_name="Time A")
    time_b = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='jogos_time_b', verbose_name="Time B")
    local = models.CharField(max_length=100, blank=True, null=True, verbose_name="Local/Quadra")
    arbitro = models.CharField(max_length=255, blank=True, null=True, verbose_name="Árbitro")
    finalizado = models.BooleanField(default=False, verbose_name="Jogo Finalizado?")
    data_hora_fim = models.DateTimeField(verbose_name="Fim Real do Jogo", blank=True, null=True)
    data_criacao = models.DateTimeField(auto_now_add=True)

    @property
    def can_file_recurso(self):
        if not self.finalizado or not self.data_hora_fim:
            return False
        from django.utils import timezone
        import datetime
        limit = self.data_hora_fim + datetime.timedelta(hours=1)
        return timezone.now() <= limit

    @property
    def presumula_deadline(self):
        if self.data_jogo and self.horario_jogo:
            from django.utils import timezone
            import datetime
            dt = datetime.datetime.combine(self.data_jogo, self.horario_jogo)
            dt_aware = timezone.make_aware(dt, timezone.get_current_timezone())
            return dt_aware - datetime.timedelta(hours=1)
        return None

    @property
    def is_presumula_deadline_passed(self):
        deadline = self.presumula_deadline
        if deadline:
            from django.utils import timezone
            return timezone.now() > deadline
        return False

    @property
    def has_wo_time_a(self):
        from django.core.exceptions import ObjectDoesNotExist
        if self.is_presumula_deadline_passed:
            try:
                return not self.presumulas.filter(representante=self.time_a).exists()
            except ObjectDoesNotExist:
                return True
        return False

    @property
    def has_wo_time_b(self):
        from django.core.exceptions import ObjectDoesNotExist
        if self.is_presumula_deadline_passed:
            try:
                return not self.presumulas.filter(representante=self.time_b).exists()
            except ObjectDoesNotExist:
                return True
        return False

    @property
    def is_finalizado_por_wo(self):
        return self.has_wo_time_a or self.has_wo_time_b

    def __str__(self):
        from django.core.exceptions import ObjectDoesNotExist
        horario_str = f" às {self.horario_jogo.strftime('%H:%M')}" if self.horario_jogo else ""
        
        try:
            nome_a = f"{self.time_a.nome_delegacao or self.time_a.email} ({self.time_a.nome_completo})"
        except ObjectDoesNotExist:
            nome_a = "Time Inexistente"
            
        try:
            nome_b = f"{self.time_b.nome_delegacao or self.time_b.email} ({self.time_b.nome_completo})"
        except ObjectDoesNotExist:
            nome_b = "Time Inexistente"
            
        return f"{self.modalidade.nome} ({self.modalidade.get_genero_display()}): {nome_a} vs {nome_b} ({self.data_jogo.strftime('%d/%m/%Y')}{horario_str})"

    def clean(self):
        super().clean()
        if self.data_jogo:
            from django.utils import timezone
            from django.core.exceptions import ValidationError
            hoje = timezone.localdate()
            
            # Valida se for criação ou se a data/horário foram alterados
            is_new = self.pk is None
            date_changed = True
            time_changed = True
            if not is_new:
                original = Jogo.objects.get(pk=self.pk)
                date_changed = original.data_jogo != self.data_jogo
                time_changed = original.horario_jogo != self.horario_jogo
                
            if is_new or date_changed or time_changed:
                if self.data_jogo < hoje:
                    raise ValidationError({'data_jogo': "A data do jogo não pode ser no passado."})
                elif self.data_jogo == hoje and self.horario_jogo:
                    agora = timezone.localtime().time()
                    if self.horario_jogo.replace(microsecond=0) < agora.replace(microsecond=0):
                        raise ValidationError({'horario_jogo': "O horário do jogo não pode ser no passado para o dia de hoje."})

    class Meta:
        verbose_name = 'Jogo'
        verbose_name_plural = 'Jogos'


class PreSumula(models.Model):
    """
    Pré-súmula diária para uma partida específica.
    """
    jogo = models.ForeignKey(Jogo, on_delete=models.CASCADE, related_name='presumulas')
    representante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='presumulas')
    tecnico = models.CharField(max_length=255, blank=True, null=True, verbose_name="Técnico da Partida")
    atletas = models.ManyToManyField(Atleta, through='PreSumulaAtleta', related_name='presumulas_escaladas')
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pré-Súmula"
        verbose_name_plural = "Pré-Súmulas"
        unique_together = ('jogo', 'representante')

    def __str__(self):
        return f"Pré-Súmula de {self.representante.nome_delegacao or self.representante.email} para o Jogo: {self.jogo}"


class PreSumulaAtleta(models.Model):
    """
    Entidade intermediária (through table) que vincula o Atleta à Pré-Súmula,
    permitindo registrar o número da camisa do jogador naquela partida.
    """
    presumula = models.ForeignKey(PreSumula, on_delete=models.CASCADE, related_name='escalacao')
    atleta = models.ForeignKey(Atleta, on_delete=models.CASCADE, related_name='escalacoes_jogos')
    numero_camisa = models.PositiveIntegerField(verbose_name="Número da Camisa")

    class Meta:
        unique_together = ('presumula', 'atleta')
        verbose_name = "Atleta Escalado"
        verbose_name_plural = "Atletas Escalados"

    def __str__(self):
        return f"Atleta {self.atleta.nome_completo} - Camisa #{self.numero_camisa}"


class Inscricao(models.Model):
    """
    Representa a inscrição geral de uma delegação.
    Reúne as modalidades que a delegação escolheu e os atletas alocados em cada uma.
    """
    STATUS_CHOICES = [
        ('pendente', 'Pendente de Análise'),
        ('deferido', 'Deferido (Aprovado)'),
        ('indeferido', 'Indeferido (Recusado)'),
    ]
    delegacao = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='inscricao')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente', verbose_name="Status da Inscrição")
    justificativa = models.TextField(blank=True, null=True, verbose_name="Justificativa")
    data_envio = models.DateTimeField(auto_now_add=True, verbose_name="Data de Envio")

    def __str__(self):
        return f"Inscrição de {self.delegacao.nome_delegacao or self.delegacao.email}"

    class Meta:
        verbose_name = "Inscrição"
        verbose_name_plural = "Inscrições"

    @property
    def atletas_inscritos(self):
        return Atleta.objects.filter(modalidades_inscritas__inscricao=self).distinct()


class InscricaoModalidade(models.Model):
    """
    Vínculo de uma modalidade específica à inscrição da delegação, contendo os respectivos atletas escalados.
    """
    inscricao = models.ForeignKey(Inscricao, on_delete=models.CASCADE, related_name='modalidades')
    modalidade = models.ForeignKey(Modalidade, on_delete=models.CASCADE, related_name='inscricoes')
    atletas = models.ManyToManyField(Atleta, related_name='modalidades_inscritas')

    def __str__(self):
        return f"{self.inscricao.delegacao.nome_delegacao or self.inscricao.delegacao.email} - {self.modalidade.nome}"

    class Meta:
        verbose_name = "Modalidade Inscrita"
        verbose_name_plural = "Modalidades Inscritas"
        unique_together = ('inscricao', 'modalidade')


class Recurso(models.Model):
    STATUS_CHOICES = [
        ('aberto', 'Aberto'),
        ('parecer_emitido', 'Parecer Emitido'),
        ('encerrado', 'Encerrado'),
    ]
    jogo = models.ForeignKey(Jogo, on_delete=models.CASCADE, related_name='recursos')
    requerente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='recursos_interpostos')
    titulo = models.CharField(max_length=255, verbose_name="Título")
    corpo = models.TextField(verbose_name="Corpo do Recurso")
    link_anexo = models.URLField(blank=True, null=True, verbose_name="Link para Anexo (Drive, etc.)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='aberto')
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Recurso"
        verbose_name_plural = "Recursos"
        ordering = ['-data_criacao']

    def __str__(self):
        return f"Recurso {self.id} - Jogo: {self.jogo} - Requerente: {self.requerente}"


class RecursoMensagem(models.Model):
    recurso = models.ForeignKey(Recurso, on_delete=models.CASCADE, related_name='mensagens')
    remetente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    texto = models.TextField(verbose_name="Mensagem")
    data_envio = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mensagem do Recurso"
        verbose_name_plural = "Mensagens dos Recursos"
        ordering = ['data_envio']

    def __str__(self):
        return f"Mensagem de {self.remetente} no Recurso {self.recurso_id}"


class Notificacao(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notificacoes')
    mensagem = models.CharField(max_length=255)
    link = models.CharField(max_length=255, blank=True, null=True)
    lida = models.BooleanField(default=False)
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notificação"
        verbose_name_plural = "Notificações"
        ordering = ['-data_criacao']

    def __str__(self):
        return f"Notificação para {self.usuario.email}: {self.mensagem}"
