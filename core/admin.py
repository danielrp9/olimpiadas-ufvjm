from django.contrib import admin
from .models import Campus, Atleta, Modalidade, Jogo, PreSumula, PreSumulaAtleta, Recurso, RecursoMensagem, Notificacao, Inscricao, InscricaoModalidade, ConfiguracaoPeriodoInscricao, SubstituicaoAtleta, CartaoPartida, RegistroDisciplinarAtleta


@admin.register(ConfiguracaoPeriodoInscricao)
class ConfiguracaoPeriodoInscricaoAdmin(admin.ModelAdmin):
    list_display = ('data_inicio', 'data_fim')


@admin.register(Campus)
class CampusAdmin(admin.ModelAdmin):
    list_display = ('nome',)
    search_fields = ('nome',)

@admin.register(Atleta)
class AtletaAdmin(admin.ModelAdmin):
    list_display = (
        'nome_completo', 
        'matricula', 
        'curso', 
        'campus', 
        'genero', 
        'tipo_atleta', 
        'cadastrado_por',
        'data_cadastro',
        'status_inscricao_display',
        'em_conformidade'
    )
    search_fields = ('nome_completo', 'matricula', 'cadastrado_por__nome_delegacao', 'cadastrado_por__email')
    list_filter = ('campus', 'curso', 'genero', 'tipo_atleta', 'em_conformidade', 'data_cadastro')

    @admin.display(description="Vínculo na Inscrição")
    def status_inscricao_display(self, obj):
        mods = list(obj.modalidades_inscritas.values_list('modalidade__nome', flat=True))
        if mods:
            return f"Inscrito em: {', '.join(mods)}"
        delegacao = obj.cadastrado_por
        inscricao = getattr(delegacao, 'inscricao', None)
        if inscricao:
            return "⚠️ Não vinculado (Adicionado fora/pós-inscrição)"
        return "Delegação sem inscrição"

@admin.register(Modalidade)
class ModalidadeAdmin(admin.ModelAdmin):
    list_display = ('nome', 'genero', 'formato_chaveamento', 'limite_minimo_jogadores', 'limite_maximo_jogadores', 'inscricoes_abertas')
    list_editable = ('inscricoes_abertas',)
    list_filter = ('genero', 'formato_chaveamento', 'inscricoes_abertas')

@admin.register(Jogo)
class JogoAdmin(admin.ModelAdmin):
    list_display = ('modalidade', 'time_a', 'time_b', 'data_jogo', 'horario_jogo', 'local', 'arbitro', 'finalizado')
    list_filter = ('modalidade', 'data_jogo', 'finalizado')
    search_fields = ('time_a__nome_delegacao', 'time_b__nome_delegacao', 'local', 'arbitro')
    raw_id_fields = ('time_a', 'time_b')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name in ("time_a", "time_b"):
            from django.contrib.auth import get_user_model
            User = get_user_model()
            kwargs["queryset"] = User.objects.filter(role='REPRESENTANTE', status_delegacao='deferido', parent_delegate__isnull=True).order_by('nome_delegacao', 'email')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

class PreSumulaAtletaInline(admin.TabularInline):
    model = PreSumulaAtleta
    extra = 1

@admin.register(PreSumula)
class PreSumulaAdmin(admin.ModelAdmin):
    list_display = ('id', 'jogo', 'representante', 'tecnico', 'data_criacao')
    list_filter = ('jogo__modalidade', 'data_criacao')
    raw_id_fields = ('representante',)
    inlines = [PreSumulaAtletaInline]
    search_fields = ('representante__nome_delegacao', 'representante__nome_completo', 'tecnico', 'jogo__modalidade__nome')
    actions = ['delete_selected', 'apagar_todas_presumulas_action']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "representante":
            from django.contrib.auth import get_user_model
            User = get_user_model()
            kwargs["queryset"] = User.objects.filter(role='REPRESENTANTE', status_delegacao='deferido', parent_delegate__isnull=True).order_by('nome_delegacao', 'email')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.action(description="Apagar TODAS as pré-súmulas do sistema")
    def apagar_todas_presumulas_action(self, request, queryset):
        count, _ = PreSumula.objects.all().delete()
        self.message_user(request, f"Todas as {count} pré-súmula(s) foram excluídas com sucesso.")

@admin.register(Recurso)
class RecursoAdmin(admin.ModelAdmin):
    list_display = ('jogo', 'requerente', 'titulo', 'status', 'data_criacao')
    list_filter = ('status', 'data_criacao')
    search_fields = ('requerente__nome_delegacao', 'requerente__email', 'titulo')

@admin.register(RecursoMensagem)
class RecursoMensagemAdmin(admin.ModelAdmin):
    list_display = ('recurso', 'remetente', 'data_envio')
    search_fields = ('recurso__titulo', 'remetente__email', 'texto')

@admin.register(Notificacao)
class NotificacaoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'mensagem', 'lida', 'data_criacao')
    list_filter = ('lida', 'data_criacao')


class InscricaoModalidadeInline(admin.StackedInline):
    model = InscricaoModalidade
    extra = 0
    filter_horizontal = ('atletas',)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "atletas":
            resolved = request.resolver_match
            if resolved and 'object_id' in resolved.kwargs:
                inscricao_id = resolved.kwargs['object_id']
                try:
                    inscricao = Inscricao.objects.get(pk=inscricao_id)
                    kwargs["queryset"] = Atleta.objects.filter(cadastrado_por=inscricao.delegacao)
                except Inscricao.DoesNotExist:
                    pass
        return super().formfield_for_manytomany(db_field, request, **kwargs)


@admin.register(Inscricao)
class InscricaoAdmin(admin.ModelAdmin):
    list_display = ('delegacao', 'status', 'data_envio')
    list_filter = ('status', 'data_envio')
    search_fields = ('delegacao__email', 'delegacao__nome_completo', 'delegacao__nome_delegacao')
    actions = ['deletar_e_resetar_delegacao']
    inlines = [InscricaoModalidadeInline]

    @admin.action(description="Excluir inscrições selecionadas e liberar representantes")
    def deletar_e_resetar_delegacao(self, request, queryset):
        count = 0
        for inscricao in queryset:
            delegacao = inscricao.delegacao
            inscricao.delete()
            delegacao.status_delegacao = 'pendente'
            delegacao.save()
            count += 1
        self.message_user(request, f"{count} inscrição(ões) excluída(s) e representante(s) correspondente(s) liberado(s) para refazer.")


@admin.register(InscricaoModalidade)
class InscricaoModalidadeAdmin(admin.ModelAdmin):
    list_display = ('inscricao', 'modalidade')
    list_filter = ('modalidade',)
    search_fields = ('inscricao__delegacao__email', 'modalidade__nome')
    filter_horizontal = ('atletas',)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "atletas":
            resolved = request.resolver_match
            if resolved and 'object_id' in resolved.kwargs:
                try:
                    insc_mod = InscricaoModalidade.objects.get(pk=resolved.kwargs['object_id'])
                    kwargs["queryset"] = Atleta.objects.filter(cadastrado_por=insc_mod.inscricao.delegacao)
                except InscricaoModalidade.DoesNotExist:
                    pass
        return super().formfield_for_manytomany(db_field, request, **kwargs)


@admin.register(SubstituicaoAtleta)
class SubstituicaoAtletaAdmin(admin.ModelAdmin):
    list_display = ('inscricao', 'atleta_saiu', 'atleta_entrou', 'data_substituicao')
    list_filter = ('data_substituicao',)
    search_fields = ('inscricao__delegacao__email', 'atleta_saiu__nome_completo', 'atleta_entrou__nome_completo')


@admin.register(CartaoPartida)
class CartaoPartidaAdmin(admin.ModelAdmin):
    list_display = ('atleta', 'tipo', 'modalidade', 'delegacao', 'partida', 'minuto', 'criado_em')
    list_filter = ('tipo', 'modalidade', 'criado_em')
    search_fields = ('atleta__nome_completo', 'delegacao__nome_delegacao', 'delegacao__email')


@admin.register(RegistroDisciplinarAtleta)
class RegistroDisciplinarAtletaAdmin(admin.ModelAdmin):
    list_display = ('atleta', 'modalidade', 'cartoes_amarelos_acumulados', 'suspenso_jogos_pendentes', 'total_amarelos_historico', 'total_vermelhos_historico')
    list_filter = ('modalidade', 'suspenso_jogos_pendentes')
    search_fields = ('atleta__nome_completo', 'atleta__matricula')


