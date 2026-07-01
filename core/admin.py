from django.contrib import admin
from .models import Campus, Atleta, Modalidade, Jogo, PreSumula, PreSumulaAtleta, Recurso, RecursoMensagem, Notificacao

@admin.register(Campus)
class CampusAdmin(admin.ModelAdmin):
    list_display = ('nome',)
    search_fields = ('nome',)

@admin.register(Atleta)
class AtletaAdmin(admin.ModelAdmin):
    list_display = ('nome_completo', 'matricula', 'curso', 'campus', 'genero', 'tipo_atleta', 'em_conformidade', 'cadastrado_por')
    search_fields = ('nome_completo', 'matricula')
    list_filter = ('campus', 'curso', 'genero', 'tipo_atleta', 'em_conformidade')

@admin.register(Modalidade)
class ModalidadeAdmin(admin.ModelAdmin):
    list_display = ('nome', 'genero', 'limite_minimo_jogadores', 'limite_maximo_jogadores', 'inscricoes_abertas')
    list_editable = ('inscricoes_abertas',)
    list_filter = ('genero', 'inscricoes_abertas')

@admin.register(Jogo)
class JogoAdmin(admin.ModelAdmin):
    list_display = ('modalidade', 'time_a', 'time_b', 'data_jogo', 'horario_jogo', 'local', 'arbitro', 'finalizado')
    list_filter = ('modalidade', 'data_jogo', 'finalizado')
    search_fields = ('time_a__nome_delegacao', 'time_b__nome_delegacao', 'local', 'arbitro')

class PreSumulaAtletaInline(admin.TabularInline):
    model = PreSumulaAtleta
    extra = 1

@admin.register(PreSumula)
class PreSumulaAdmin(admin.ModelAdmin):
    list_display = ('jogo', 'representante', 'tecnico', 'data_criacao')
    inlines = [PreSumulaAtletaInline]
    search_fields = ('representante__nome_delegacao', 'representante__nome_completo', 'tecnico')

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
