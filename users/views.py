from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth import login as auth_login, logout as auth_logout, get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.edit import FormView
from django.urls import reverse_lazy
from django.contrib import messages
from django.core.exceptions import PermissionDenied

from users.models import ComissaoWhitelist, MembroDelegacao
from users.forms import CompleteProfileForm
from users.utils.oauth_google import get_google_auth_url, get_google_user_info

User = get_user_model()

class GoogleLoginView(View):
    """
    Inicia o fluxo de login social, redirecionando o usuário para o Google.
    """
    def get(self, request):
        auth_url = get_google_auth_url()
        return redirect(auth_url)


class GoogleCallbackView(View):
    """
    Recebe o callback do Google, valida as credenciais via OIDC (OpenID Connect),
    verifica a Whitelist da Comissão e autentica/registra o usuário.
    """
    def get(self, request):
        code = request.GET.get('code')
        error = request.GET.get('error')
        
        if error or not code:
            messages.error(request, f"Erro na autenticação com o Google: {error or 'Código ausente'}")
            return redirect('login')
            
        try:
            # 1. Busca informações do usuário no Google
            google_user = get_google_user_info(code)
            email = google_user['email']
            
            # Garante que o e-mail seja verificado pelo Google
            if not google_user.get('email_verified', False):
                messages.error(request, "Este e-mail do Google não foi verificado e não pode ser utilizado.")
                return redirect('login')
            
            # 2. Checa se o e-mail está na Whitelist da Comissão
            is_in_whitelist = ComissaoWhitelist.objects.filter(email__iexact=email).exists()
            
            # 2b. Checa se o e-mail é membro autorizado de alguma delegação
            membro_autorizado = MembroDelegacao.objects.filter(email__iexact=email).first()
            
            # 3. Tenta localizar ou criar o usuário
            user = User.objects.filter(email__iexact=email).first()
            
            if user is None:
                # Primeiro Acesso: Registra novo usuário
                if is_in_whitelist:
                    role = 'COMISSAO'
                    parent_delegate = None
                elif membro_autorizado:
                    role = 'REPRESENTANTE'
                    parent_delegate = membro_autorizado.delegado_principal
                else:
                    role = 'REPRESENTANTE'
                    parent_delegate = None
                
                user = User.objects.create_user(
                    email=email,
                    nome_completo=google_user['nome_completo'],
                    foto_url=google_user['foto_url'],
                    google_id=google_user['google_id'],
                    role=role,
                    parent_delegate=parent_delegate,
                )
                messages.success(request, f"Cadastro realizado com sucesso como {user.get_role_display()}!")
            else:
                # Usuário já existente: Atualiza dados do Google (Foto, Nome) e o google_id se necessário
                user.nome_completo = google_user['nome_completo']
                user.foto_url = google_user['foto_url']
                if not user.google_id:
                    user.google_id = google_user['google_id']
                
                # Sincroniza o papel e vinculo de delegação do usuário
                if is_in_whitelist:
                    if user.role != 'COMISSAO':
                        user.role = 'COMISSAO'
                        user.is_staff = True
                        messages.info(request, "Seu acesso foi atualizado para a Comissão Organizadora.")
                    user.parent_delegate = None
                elif membro_autorizado:
                    user.role = 'REPRESENTANTE'
                    user.parent_delegate = membro_autorizado.delegado_principal
                    user.is_staff = False
                else:
                    if user.role == 'COMISSAO' and not user.is_superuser:
                        user.role = 'REPRESENTANTE'
                        user.is_staff = False
                        messages.warning(request, "Seu acesso de comissão expirou. Agora você é um Representante.")
                    # Caso não esteja na whitelist nem autorizado, mas já tivesse parent_delegate, limpamos se o admin removeu
                    user.parent_delegate = None
                
                user.save()
                
            # 4. Efetua o login na sessão do Django
            auth_login(request, user)
            
            # 5. Redirecionamento condicional (Fluxo de 2 Etapas)
            if not user.perfil_completo:
                messages.warning(request, "Por favor, complete o seu perfil informando o CPF.")
                return redirect('complete_profile')
                
            # Se perfil completo, redireciona para a página principal
            return redirect('dashboard')
            
        except PermissionDenied as e:
            messages.error(request, str(e))
            return redirect('login')
        except Exception as e:
            # Em produção, registre o log do erro
            messages.error(request, "Ocorreu um erro interno durante a autenticação. Tente novamente.")
            return redirect('login')


class CompleteProfileView(LoginRequiredMixin, FormView):
    """
    Tela de "Completar Perfil" (Segunda Etapa).
    Obrigatória para Representantes que ainda não informaram o CPF.
    """
    template_name = 'users/complete_profile.html'
    form_class = CompleteProfileForm
    success_url = reverse_lazy('dashboard')

    def get_form_kwargs(self):
        # Passa a instância do usuário logado para o formulário
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = self.request.user
        return kwargs

    def dispatch(self, request, *args, **kwargs):
        # Se o usuário já tiver perfil completo, não precisa desta tela
        if request.user.is_authenticated and request.user.perfil_completo:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # Salva o formulário (CPF é atualizado e perfil_completo é setado como True no save do User)
        form.save()
        messages.success(self.request, "Perfil completado com sucesso! Acesso liberado.")
        return super().form_valid(form)


class LogoutView(View):
    """
    Encerra a sessão do usuário.
    """
    def get(self, request):
        auth_logout(request)
        messages.info(request, "Sessão encerrada com sucesso.")
        return redirect('login')
