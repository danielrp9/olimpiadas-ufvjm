from django.contrib import admin
from .models import MembroComissao, HistoricoEmissao


@admin.register(MembroComissao)
class MembroComissaoAdmin(admin.ModelAdmin):
    list_display = ('nome_completo', 'matricula', 'cargo', 'email', 'ativo', 'criado_em')
    list_filter = ('cargo', 'ativo')
    search_fields = ('nome_completo', 'matricula', 'email')


@admin.register(HistoricoEmissao)
class HistoricoEmissaoAdmin(admin.ModelAdmin):
    list_display = ('tipo', 'total_documentos', 'carga_horaria', 'periodo', 'cidade_data', 'solicitado_por', 'data_emissao')
    list_filter = ('tipo', 'data_emissao')
    search_fields = ('periodo', 'cidade_data')
    readonly_fields = ('data_emissao',)
