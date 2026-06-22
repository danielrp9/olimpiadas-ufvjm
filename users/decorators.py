from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

def role_required(allowed_roles):
    """
    Decorador para rotas que exige que o usuário tenha um dos papéis informados.
    Se o usuário não for autenticado, é redirecionado para o login.
    Se não possuir o papel ou o perfil não estiver completo, retorna 403 (Permission Denied).
    """
    if isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # 1. Verifica autenticação
            if not request.user.is_authenticated:
                return redirect('login')
            
            # 2. Verifica se o papel está autorizado
            if request.user.role not in allowed_roles:
                raise PermissionDenied("Acesso não autorizado para o seu papel.")
            
            # 3. Se for Representante, verifica se completou o cadastro (CPF)
            if request.user.role == 'REPRESENTANTE' and not request.user.perfil_completo:
                # Se estiver tentando acessar a própria página de completar perfil, permite
                if request.resolver_match.url_name != 'complete_profile':
                    return redirect('complete_profile')

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def comissao_required(view_func):
    """
    Decorador específico para proteger views administrativas restritas à COMISSAO.
    """
    return role_required('COMISSAO')(view_func)


def representante_required(view_func):
    """
    Decorador específico para proteger views restritas a REPRESENTANTEs de delegação.
    """
    return role_required('REPRESENTANTE')(view_func)
