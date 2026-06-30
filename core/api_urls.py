from django.urls import path
from . import api_views

urlpatterns = [
    # Auth
    path('auth/me/', api_views.APIAuthMeView.as_view(), name='api_auth_me'),
    path('auth/login/', api_views.APIAuthLoginView.as_view(), name='api_auth_login'),
    path('auth/logout/', api_views.APIAuthLogoutView.as_view(), name='api_auth_logout'),
    path('auth/complete-profile/', api_views.APIAuthCompleteProfileView.as_view(), name='api_auth_complete_profile'),
    
    # Dashboard
    path('dashboard/', api_views.APIDashboardView.as_view(), name='api_dashboard'),
    
    # Atletas
    path('atletas/', api_views.APIAtletasView.as_view(), name='api_atletas'),
    path('atletas/<int:pk>/', api_views.APIAtletaDetailView.as_view(), name='api_atleta_detail'),
    path('atletas/<int:pk>/enviar-correcao/', api_views.APIAtletaEnviarCorrecaoView.as_view(), name='api_atleta_enviar_correcao'),
    path('atletas/<int:pk>/reset-conformidade/', api_views.APIAtletaResetConformidadeView.as_view(), name='api_atleta_reset_conformidade'),
    path('atletas/<int:pk>/avaliar/', api_views.APIAtletaAvaliarView.as_view(), name='api_atleta_avaliar'),
    
    # Modalidades
    path('modalidades/', api_views.APIModalidadesView.as_view(), name='api_modalidades'),
    path('modalidades/<int:pk>/', api_views.APIModalidadeDetailView.as_view(), name='api_modalidade_detail'),
    path('modalidades/<int:pk>/toggle/', api_views.APIModalidadeToggleView.as_view(), name='api_modalidade_toggle'),
    
    # Jogos
    path('jogos/', api_views.APIJogosView.as_view(), name='api_jogos'),
    path('jogos/<int:pk>/', api_views.APIJogoDetailView.as_view(), name='api_jogo_detail'),
    
    # Delegações
    path('delegacoes/', api_views.APIDelegacoesView.as_view(), name='api_delegacoes'),
    path('delegacoes/<int:pk>/avaliar/', api_views.APIDelegacaoAvaliarView.as_view(), name='api_delegacao_avaliar'),
    
    # Pré-Súmulas
    path('presumulas/', api_views.APIPreSumulasView.as_view(), name='api_presumulas'),
    path('presumulas/<int:pk>/', api_views.APIPreSumulaDetailView.as_view(), name='api_presumula_detail'),
    
    # Inscrição
    path('inscricao/', api_views.APIInscricaoFluxoView.as_view(), name='api_inscricao'),
    path('inscricao/refazer/', api_views.APIInscricaoRefazerView.as_view(), name='api_inscricao_refazer'),
    
    # Whitelist
    path('whitelist/', api_views.APIWhitelistView.as_view(), name='api_whitelist'),
    path('whitelist/<int:pk>/', api_views.APIWhitelistDetailView.as_view(), name='api_whitelist_detail'),
]
