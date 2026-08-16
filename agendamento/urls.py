from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_agendamento_view, name='agendamento_dashboard'),
    path('datas/', views.datas_list_view, name='agendamento_datas'),
    path('datas/<int:pk>/edit/', views.data_edit_view, name='agendamento_data_edit'),
    path('datas/<int:pk>/delete/', views.data_delete_view, name='agendamento_data_delete'),
    path('recursos/', views.recursos_list_view, name='agendamento_recursos'),
    path('recursos/<int:pk>/edit/', views.recurso_edit_view, name='agendamento_recurso_edit'),
    path('recursos/<int:pk>/delete/', views.recurso_delete_view, name='agendamento_recurso_delete'),
    path('fases/', views.fases_config_view, name='agendamento_fases'),
    path('fases/nova/', views.fase_create_view, name='agendamento_fase_create'),
    path('fases/<int:pk>/delete/', views.fase_delete_view, name='agendamento_fase_delete'),
    path('regras/', views.regras_config_view, name='agendamento_regras'),
    path('gerar/', views.gerar_cronograma_view, name='agendamento_gerar'),
    path('resetar/', views.resetar_horarios_view, name='agendamento_resetar_horarios'),
    path('cenarios/<int:pk>/', views.cenario_detalhe_view, name='agendamento_cenario_detalhe'),
    path('cenarios/<int:pk>/aplicar/', views.aplicar_cenario_view, name='agendamento_aplicar_cenario'),
    path('cenarios/<int:pk>/delete/', views.cenario_delete_view, name='agendamento_cenario_delete'),
    path('auditoria/', views.relatorio_auditoria_view, name='agendamento_auditoria'),
]
