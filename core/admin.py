from django.contrib import admin
from .models import Atleta, Modalidade, Jogo, PreSumula, PreSumulaAtleta

@admin.register(Atleta)
class AtletaAdmin(admin.ModelAdmin):
    list_display = ('nome_completo', 'matricula', 'curso', 'campus', 'genero', 'em_conformidade', 'cadastrado_por')
    search_fields = ('nome_completo', 'matricula')
    list_filter = ('campus', 'curso', 'genero', 'em_conformidade')

@admin.register(Modalidade)
class ModalidadeAdmin(admin.ModelAdmin):
    list_display = ('nome', 'genero', 'limite_minimo_jogadores', 'limite_maximo_jogadores', 'inscricoes_abertas')
    list_editable = ('inscricoes_abertas',)
    list_filter = ('genero', 'inscricoes_abertas')

@admin.register(Jogo)
class JogoAdmin(admin.ModelAdmin):
    list_display = ('modalidade', 'time_a', 'time_b', 'data_jogo', 'horario_jogo', 'local', 'finalizado')
    list_filter = ('modalidade', 'data_jogo', 'finalizado')
    search_fields = ('time_a__nome_delegacao', 'time_b__nome_delegacao', 'local')

class PreSumulaAtletaInline(admin.TabularInline):
    model = PreSumulaAtleta
    extra = 1

@admin.register(PreSumula)
class PreSumulaAdmin(admin.ModelAdmin):
    list_display = ('jogo', 'representante', 'data_criacao')
    inlines = [PreSumulaAtletaInline]
    search_fields = ('representante__nome_delegacao', 'representante__nome_completo')
