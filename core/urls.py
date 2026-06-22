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
    


    # Painel da Comissão (Admin UI)
    path('comissao/modalidades/', views.AdminModalidadeListView.as_view(), name='admin_modalidades'),
    path('comissao/modalidade/nova/', views.ModalidadeCreateView.as_view(), name='modalidade_create'),
    path('comissao/modalidade/<int:pk>/editar/', views.ModalidadeUpdateView.as_view(), name='modalidade_update'),
    path('comissao/modalidade/<int:pk>/remover/', views.ModalidadeDeleteView.as_view(), name='modalidade_delete'),
    path('comissao/modalidade/<int:pk>/toggle/', views.toggle_modalidade, name='toggle_modalidade'),
    path('comissao/jogo/novo/', views.JogoCreateView.as_view(), name='jogo_create'),
    path('comissao/jogo/<int:pk>/editar/', views.JogoUpdateView.as_view(), name='jogo_update'),
    path('comissao/jogo/<int:pk>/remover/', views.JogoDeleteView.as_view(), name='jogo_delete'),
    path('comissao/whitelist/', views.AdminWhitelistView.as_view(), name='admin_whitelist'),
    path('comissao/whitelist/<int:pk>/remover/', views.whitelist_delete, name='whitelist_delete'),
    path('comissao/atleta/<int:pk>/reset-conformidade/', views.reset_conformidade_atleta, name='atleta_reset_conformidade'),
    path('atleta/<int:pk>/enviar-correcao/', views.enviar_correcao_atleta, name='enviar_correcao_atleta'),

    # Rotas de Gestão de Delegações (COMISSAO)
    path('comissao/delegacoes/', views.AdminDelegacaoListView.as_view(), name='admin_delegacoes'),
    path('comissao/delegacao/<int:pk>/avaliar/', views.avaliar_delegacao, name='avaliar_delegacao'),
    path('comissao/atleta/<int:pk>/avaliar/', views.avaliar_atleta, name='avaliar_atleta'),

    # Rotas de Pré-Súmulas (REPRESENTANTE e COMISSAO)
    path('presumulas/', views.PreSumulaListView.as_view(), name='presumula_list'),
    path('presumula/criar/', views.PreSumulaCreateView.as_view(), name='presumula_create'),
    path('presumula/<int:pk>/', views.PreSumulaDetailView.as_view(), name='presumula_detail'),
    path('presumula/<int:pk>/editar/', views.PreSumulaUpdateView.as_view(), name='presumula_update'),
]
