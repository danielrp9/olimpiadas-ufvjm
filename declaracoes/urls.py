from django.urls import path
from . import views

urlpatterns = [
    path('', views.declaracoes_index_view, name='declaracoes_index'),
    path('previa/', views.previa_declaracao_view, name='declaracoes_previa'),
    path('iniciar/', views.iniciar_geracao_view, name='declaracoes_iniciar'),
    path('progresso/<str:task_id>/', views.progresso_geracao_view, name='declaracoes_progresso'),
    path('download/<str:task_id>/', views.download_zip_view, name='declaracoes_download'),
    path('comissao/salvar/', views.salvar_membro_comissao_view, name='declaracoes_comissao_salvar'),
    path('comissao/excluir/<int:membro_id>/', views.excluir_membro_comissao_view, name='declaracoes_comissao_excluir'),
    path('comissao/sincronizar/', views.sincronizar_comissao_view, name='declaracoes_comissao_sincronizar'),
]
