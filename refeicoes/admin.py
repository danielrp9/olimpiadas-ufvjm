from django.contrib import admin
from .models import RefeicaoAgendada, RegistroRefeicao


@admin.register(RefeicaoAgendada)
class RefeicaoAgendadaAdmin(admin.ModelAdmin):
    list_display = ('data', 'tipo', 'ativo', 'get_campi', 'criado_em')
    list_filter = ('tipo', 'ativo', 'data', 'campi_liberados')
    filter_horizontal = ('campi_liberados',)

    def get_campi(self, obj):
        return ", ".join([c.nome for c in obj.campi_liberados.all()])
    get_campi.short_description = "Campi Liberados"


@admin.register(RegistroRefeicao)
class RegistroRefeicaoAdmin(admin.ModelAdmin):
    list_display = ('atleta', 'get_campus', 'refeicao', 'data_retirada', 'validado_por')
    list_filter = ('refeicao__tipo', 'refeicao__data', 'atleta__campus')
    search_fields = ('atleta__nome_completo', 'atleta__cpf', 'atleta__matricula')
    readonly_fields = ('data_retirada',)

    def get_campus(self, obj):
        return obj.atleta.campus.nome if obj.atleta.campus else "-"
    get_campus.short_description = "Campus"
