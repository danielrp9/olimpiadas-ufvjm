from django.contrib import admin
from .models import (
    ConfiguracaoGeral, DataDisponivel, RecursoLocal,
    ParametroModalidade, RestricaoFase, CenarioExecucao, ItemAlocacao
)


class DataDisponivelInline(admin.TabularInline):
    model = DataDisponivel
    extra = 1


class RecursoLocalInline(admin.TabularInline):
    model = RecursoLocal
    extra = 1


class RestricaoFaseInline(admin.TabularInline):
    model = RestricaoFase
    extra = 1


@admin.register(ConfiguracaoGeral)
class ConfiguracaoGeralAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativo', 'intervalo_padrao_minutos', 'descanso_minimo_equipe_minutos', 'duracao_padrao_jogo_minutos', 'criado_em')
    list_filter = ('ativo',)
    inlines = [DataDisponivelInline, RecursoLocalInline, RestricaoFaseInline]


@admin.register(DataDisponivel)
class DataDisponivelAdmin(admin.ModelAdmin):
    list_display = ('data', 'horario_inicio', 'horario_fim', 'configuracao', 'ativo')
    list_filter = ('configuracao', 'ativo')
    ordering = ('data',)


@admin.register(RecursoLocal)
class RecursoLocalAdmin(admin.ModelAdmin):
    list_display = ('nome', 'configuracao', 'ordem', 'ativo')
    list_filter = ('configuracao', 'ativo')
    filter_horizontal = ('modalidades_permitidas',)


@admin.register(RestricaoFase)
class RestricaoFaseAdmin(admin.ModelAdmin):
    list_display = ('fase_codigo', 'fase_nome', 'modalidade', 'ordem_precedencia', 'configuracao')
    list_filter = ('configuracao', 'modalidade')
    filter_horizontal = ('datas_permitidas',)


@admin.register(CenarioExecucao)
class CenarioExecucaoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'status', 'configuracao', 'criado_em')
    list_filter = ('status', 'configuracao')


@admin.register(ItemAlocacao)
class ItemAlocacaoAdmin(admin.ModelAdmin):
    list_display = ('modalidade_nome', 'fase_display', 'data_alocada', 'horario_inicio', 'recurso_nome', 'time_a_nome', 'time_b_nome')
    list_filter = ('data_alocada', 'recurso_nome', 'modalidade_nome', 'fase_codigo')
