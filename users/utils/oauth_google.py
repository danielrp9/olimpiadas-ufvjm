import urllib.parse
import requests
from django.conf import settings
from django.core.exceptions import PermissionDenied

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

def get_google_auth_url() -> str:
    """
    Gera a URL de redirecionamento para o fluxo de login do Google OAuth 2.0.
    """
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

def get_google_user_info(code: str) -> dict:
    """
    Troca o código de autorização obtido pelo token de acesso e busca
    as informações do perfil do usuário no Google (OpenID Connect).
    """
    # 1. Troca o código pelo access token
    token_data = {
        "code": code,
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    
    token_response = requests.post(GOOGLE_TOKEN_URL, data=token_data)
    if not token_response.ok:
        raise PermissionDenied("Falha ao obter token de acesso do Google.")
        
    tokens = token_response.json()
    access_token = tokens.get("access_token")
    
    # 2. Busca informações do perfil do usuário
    headers = {"Authorization": f"Bearer {access_token}"}
    userinfo_response = requests.get(GOOGLE_USERINFO_URL, headers=headers)
    if not userinfo_response.ok:
        raise PermissionDenied("Falha ao recuperar informações de perfil do Google.")
        
    user_info = userinfo_response.json()
    
    # Mapeia as informações do Google para os nomes dos campos que utilizaremos
    return {
        "google_id": user_info.get("sub"),
        "email": user_info.get("email"),
        "nome_completo": user_info.get("name"),
        "foto_url": user_info.get("picture"),
        "email_verified": user_info.get("email_verified", False),
    }
