from django.contrib import admin
from .models import Atleta, Modalidade, Equipe

@admin.register(Atleta)
class AtletaAdmin(admin.ModelAdmin):
    list_display = ('nome_completo', 'matricula', 'curso', 'campus', 'cadastrado_por')
    search_fields = ('nome_completo', 'matricula')
    list_filter = ('campus', 'curso')

@admin.register(Modalidade)
class ModalidadeAdmin(admin.ModelAdmin):
    list_display = ('nome', 'limite_minimo_jogadores', 'limite_maximo_jogadores', 'inscricoes_abertas')
    list_editable = ('inscricoes_abertas',)

@admin.register(Equipe)
class EquipeAdmin(admin.ModelAdmin):
    list_display = ('nome_equipe', 'modalidade', 'representante', 'data_inscricao')
    search_fields = ('nome_equipe',)
    list_filter = ('modalidade',)
