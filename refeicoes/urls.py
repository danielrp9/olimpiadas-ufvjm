from django.urls import path
from . import views

urlpatterns = [
    path('gerenciar/', views.gerenciar_refeicoes_view, name='refeicoes_gerenciar'),
    path('editar/<int:refeicao_id>/', views.editar_refeicao_view, name='refeicoes_editar'),
    path('toggle/<int:refeicao_id>/', views.toggle_refeicao_ativa_view, name='refeicoes_toggle_ativa'),
    path('validar/', views.validar_refeicao_view, name='refeicoes_validar'),
    path('api/buscar-atletas/', views.api_buscar_atletas, name='refeicoes_api_buscar_atletas'),
    path('api/processar-validacao/', views.api_processar_validacao, name='refeicoes_api_processar_validacao'),
    path('relatorio/', views.relatorio_refeicoes_view, name='refeicoes_relatorio'),
    path('relatorio/exportar/', views.exportar_relatorio_refeicoes_view, name='refeicoes_relatorio_exportar'),
]
