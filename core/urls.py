from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('regulamento/', views.RegulamentoView.as_view(), name='regulamento'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Atletas
    path('atletas/', views.AtletaListView.as_view(), name='atleta_list'),
    path('atletas/adicionar/', views.AtletaBulkCreateView.as_view(), name='atleta_bulk_create'),
    path('atleta/<int:pk>/editar/', views.AtletaUpdateView.as_view(), name='atleta_update'),
    path('atleta/<int:pk>/remover/', views.AtletaDeleteView.as_view(), name='atleta_delete'),
    
    # Inscrições
    path('modalidades/', views.ModalidadeListView.as_view(), name='modalidade_list'),
    path('modalidade/<int:modalidade_id>/inscrever/', views.EquipeCreateView.as_view(), name='equipe_create'),
    path('equipe/<int:pk>/', views.EquipeDetailView.as_view(), name='equipe_detail'),
    path('equipe/<int:pk>/editar/', views.EquipeUpdateView.as_view(), name='equipe_update'),
    path('equipe/<int:pk>/remover/', views.EquipeDeleteView.as_view(), name='equipe_delete'),
    path('equipe/<int:equipe_id>/solicitar-inclusao/', views.SolicitacaoInclusaoCreateView.as_view(), name='solicitar_inclusao'),

    # Painel da Comissão (Admin UI)
    path('comissao/modalidades/', views.AdminModalidadeListView.as_view(), name='admin_modalidades'),
    path('comissao/modalidade/nova/', views.ModalidadeCreateView.as_view(), name='modalidade_create'),
    path('comissao/modalidade/<int:pk>/editar/', views.ModalidadeUpdateView.as_view(), name='modalidade_update'),
    path('comissao/modalidade/<int:pk>/remover/', views.ModalidadeDeleteView.as_view(), name='modalidade_delete'),
    path('comissao/equipes/', views.AdminEquipeListView.as_view(), name='admin_equipes'),
    path('comissao/modalidade/<int:pk>/toggle/', views.toggle_modalidade, name='toggle_modalidade'),
    path('comissao/equipe/<int:pk>/avaliar/', views.avaliar_equipe, name='avaliar_equipe'),
    path('comissao/solicitacao/<int:pk>/avaliar/', views.avaliar_solicitacao, name='avaliar_solicitacao'),
    path('comissao/atleta/<int:pk>/reset-conformidade/', views.reset_conformidade_atleta, name='atleta_reset_conformidade'),
    path('atleta/<int:pk>/enviar-correcao/', views.enviar_correcao_atleta, name='enviar_correcao_atleta'),
]
