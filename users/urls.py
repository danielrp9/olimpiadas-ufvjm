from django.urls import path
from users.views import GoogleLoginView, GoogleCallbackView, CompleteProfileView, LogoutView

urlpatterns = [
    # Rotas de Autenticação Social via Google OAuth 2.0
    path('login/google/', GoogleLoginView.as_view(), name='google_login'),
    path('auth/callback/', GoogleCallbackView.as_view(), name='google_callback'),
    
    # Segunda Etapa: Completar cadastro do Representante
    path('perfil/completar/', CompleteProfileView.as_view(), name='complete_profile'),
    
    # Encerramento de sessão
    path('logout/', LogoutView.as_view(), name='logout'),
]
