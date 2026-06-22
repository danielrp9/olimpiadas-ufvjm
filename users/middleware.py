from django.shortcuts import redirect
from django.urls import reverse

class ProfileCompletionMiddleware:
    """
    Middleware para garantir o fluxo de cadastro em duas etapas.
    Se um usuário estiver logado e seu perfil estiver incompleto (ex: Representante sem CPF),
    ele será redirecionado para a página de completar perfil.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Se não estiver logado, segue o fluxo normal (decoradores de login cuidam disso)
        if not request.user.is_authenticated:
            return self.get_response(request)

        # 2. Se o perfil já estiver completo, segue o fluxo normal
        if request.user.perfil_completo:
            return self.get_response(request)

        # 3. Lista de URLs isentas de redirecionamento para evitar loop infinito
        exempt_urls = [
            reverse('complete_profile'),
            reverse('logout'),
            # Se existirem outras urls de autenticação, coloque-as aqui
        ]
        
        # Também isenta URLs de autenticação social e arquivos estáticos/media
        path = request.path
        if (
            path in exempt_urls or 
            path.startswith('/static/') or 
            path.startswith('/media/') or 
            path.startswith('/auth/') or 
            path.startswith('/__debug__/') or
            path.startswith('/admin/') # permite que admins gerenciem a whitelist sem problemas
        ):
            return self.get_response(request)

        # 4. Redireciona obrigatoriamente para preencher o perfil
        return redirect('complete_profile')
