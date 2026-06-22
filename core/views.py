from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import login, logout
from django.urls import reverse_lazy
from django.contrib import messages
from .models import Atleta, Modalidade, Jogo, PreSumula, PreSumulaAtleta
from .forms import RegisterForm, AtletaForm, JogoForm
from users.models import ComissaoWhitelist

class RegisterView(CreateView):
    form_class = RegisterForm
    template_name = 'registration/register.html'
    success_url = reverse_lazy('dashboard')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response

def logout_view(request):
    logout(request)
    return redirect('login')

from django.contrib.auth import get_user_model
User = get_user_model()
from django.contrib.auth.decorators import user_passes_test, login_required
from django.utils.decorators import method_decorator

# ... (rest of imports unchanged)

from django.db.models import Count, Q

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'core/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        if user.is_staff:
            context['is_admin'] = True
            context['total_atletas_global'] = Atleta.objects.count()
            context['total_usuarios'] = User.objects.filter(role='REPRESENTANTE').count()
            context['total_presumulas_global'] = PreSumula.objects.count()
            context['ultimas_presumulas'] = PreSumula.objects.all().order_by('-data_criacao')[:10]
            
            # Estatísticas por Modalidade baseadas em Pré-Súmulas
            context['stats_modalidade'] = Modalidade.objects.annotate(
                num_presumulas=Count('jogos__presumulas')
            ).order_by('-num_presumulas')
            
            # Estatísticas por Campus (Baseado nos Atletas)
            context['stats_campus'] = Atleta.objects.values('campus').annotate(
                total=Count('id')
            ).order_by('-total')
            
            # Estatísticas por Atlética/Delegação
            context['stats_atletica'] = User.objects.filter(role='REPRESENTANTE').annotate(
                num_atletas=Count('atletas'),
                num_presumulas=Count('presumulas')
            ).order_by('-num_atletas')
            
            return context
        
        context['is_admin'] = False
        context['total_atletas'] = Atleta.objects.filter(cadastrado_por=user).count()
        context['minhas_presumulas'] = PreSumula.objects.filter(representante=user).order_by('-jogo__data_jogo')
        context['modalidades_abertas'] = Modalidade.objects.filter(inscricoes_abertas=True)
        return context

@method_decorator(user_passes_test(lambda u: u.is_staff), name='dispatch')
class AdminModalidadeListView(LoginRequiredMixin, ListView):
    model = Modalidade
    template_name = 'core/admin_modalidades.html'
    context_object_name = 'modalidades'

@method_decorator(user_passes_test(lambda u: u.is_staff), name='dispatch')
class ModalidadeCreateView(LoginRequiredMixin, CreateView):
    model = Modalidade
    fields = ['nome', 'genero', 'limite_minimo_jogadores', 'limite_maximo_jogadores', 'inscricoes_abertas']
    template_name = 'core/modalidade_form.html'
    success_url = reverse_lazy('admin_modalidades')

    def form_valid(self, form):
        messages.success(self.request, "Modalidade criada com sucesso!")
        return super().form_valid(form)

@method_decorator(user_passes_test(lambda u: u.is_staff), name='dispatch')
class ModalidadeUpdateView(LoginRequiredMixin, UpdateView):
    model = Modalidade
    fields = ['nome', 'genero', 'limite_minimo_jogadores', 'limite_maximo_jogadores', 'inscricoes_abertas']
    template_name = 'core/modalidade_form.html'
    success_url = reverse_lazy('admin_modalidades')

    def form_valid(self, form):
        messages.success(self.request, "Modalidade atualizada com sucesso!")
        return super().form_valid(form)

@method_decorator(user_passes_test(lambda u: u.is_staff), name='dispatch')
class ModalidadeDeleteView(LoginRequiredMixin, DeleteView):
    model = Modalidade
    template_name = 'core/confirm_delete.html'
    success_url = reverse_lazy('admin_modalidades')

# Remoção de AdminEquipeListView de inscrições legadas

@user_passes_test(lambda u: u.is_staff)
def toggle_modalidade(request, pk):
    modalidade = get_object_or_404(Modalidade, pk=pk)
    modalidade.inscricoes_abertas = not modalidade.inscricoes_abertas
    modalidade.save()
    messages.success(request, f"Status da modalidade {modalidade.nome} alterado!")
    return redirect('admin_modalidades')

@method_decorator(user_passes_test(lambda u: u.is_staff), name='dispatch')
class JogoCreateView(LoginRequiredMixin, CreateView):
    model = Jogo
    form_class = JogoForm
    template_name = 'core/jogo_form.html'
    success_url = reverse_lazy('presumula_list')

    def form_valid(self, form):
        messages.success(self.request, "Jogo lançado com sucesso! A pré-súmula está agora aberta para as delegações correspondentes.")
        return super().form_valid(form)

@method_decorator(user_passes_test(lambda u: u.is_staff), name='dispatch')
class JogoUpdateView(LoginRequiredMixin, UpdateView):
    model = Jogo
    form_class = JogoForm
    template_name = 'core/jogo_form.html'
    success_url = reverse_lazy('presumula_list')

    def form_valid(self, form):
        messages.success(self.request, "Dados do jogo atualizados com sucesso!")
        return super().form_valid(form)

@method_decorator(user_passes_test(lambda u: u.is_staff), name='dispatch')
class JogoDeleteView(LoginRequiredMixin, DeleteView):
    model = Jogo
    template_name = 'core/confirm_delete.html'
    success_url = reverse_lazy('presumula_list')

    def form_valid(self, form):
        messages.success(self.request, "Jogo excluído com sucesso!")
        return super().form_valid(form)

class RegulamentoView(TemplateView):
    template_name = 'core/regulamento.html'

# Remoção de avaliar_equipe de inscrições legadas

@login_required
def enviar_correcao_atleta(request, pk):
    atleta = get_object_or_404(Atleta, pk=pk, cadastrado_por=request.user)
    if not atleta.permite_correcao:
        messages.error(request, "Este atleta não está habilitado para correções.")
        return redirect(request.META.get('HTTP_REFERER', 'dashboard'))
        
    if request.method == 'POST':
        novo_link = request.POST.get('link_correcao')
        if novo_link:
            atleta.link_correcao = novo_link
            atleta.save()
            messages.success(request, "Documento de correção enviado. A comissão fará a reavaliação.")
            
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))

@user_passes_test(lambda u: u.is_staff)
def reset_conformidade_atleta(request, pk):
    atleta = get_object_or_404(Atleta, pk=pk)
    atleta.em_conformidade = True
    atleta.justificativa_inconformidade = ""
    atleta.save()
    messages.success(request, f"Atleta {atleta.nome_completo} restaurado para conformidade!")
    return redirect(request.META.get('HTTP_REFERER', 'admin_delegacoes'))

# Atletas Views
class AtletaListView(LoginRequiredMixin, ListView):
    model = Atleta
    template_name = 'core/atleta_list.html'
    context_object_name = 'atletas'

    def get_queryset(self):
        return Atleta.objects.filter(cadastrado_por=self.request.user)

class AtletaBulkCreateView(LoginRequiredMixin, TemplateView):
    template_name = 'core/atleta_bulk_form.html'

    def post(self, request, *args, **kwargs):
        nomes = request.POST.getlist('nome[]')
        cpfs = request.POST.getlist('cpf[]')
        emails = request.POST.getlist('email[]')
        matriculas = request.POST.getlist('matricula[]')
        cursos = request.POST.getlist('curso[]')
        campi = request.POST.getlist('campus[]')
        generos = request.POST.getlist('genero[]')
        is_egressos = request.POST.getlist('is_egresso[]')
        links_egressos = request.POST.getlist('link_egresso[]')

        atletas_criados = 0
        for i in range(len(nomes)):
            if nomes[i].strip():
                is_egr = (is_egressos[i] == '1') if i < len(is_egressos) else False
                link_egr = links_egressos[i] if i < len(links_egressos) else ''
                gen = generos[i] if i < len(generos) else 'M'
                
                Atleta.objects.create(
                    nome_completo=nomes[i],
                    cpf=cpfs[i] if i < len(cpfs) else '',
                    email=emails[i],
                    matricula=matriculas[i],
                    curso=cursos[i],
                    campus=campi[i],
                    genero=gen,
                    is_egresso=is_egr,
                    link_documento_egresso=link_egr,
                    cadastrado_por=request.user
                )
                atletas_criados += 1
        
        if atletas_criados > 0:
            messages.success(request, f"{atletas_criados} atletas cadastrados com sucesso!")
        return redirect('atleta_list')

class AtletaUpdateView(LoginRequiredMixin, UpdateView):
    model = Atleta
    form_class = AtletaForm
    template_name = 'core/atleta_form.html'
    success_url = reverse_lazy('atleta_list')

    def get_queryset(self):
        return Atleta.objects.filter(cadastrado_por=self.request.user)

class AtletaDeleteView(LoginRequiredMixin, DeleteView):
    model = Atleta
    template_name = 'core/confirm_delete.html'
    success_url = reverse_lazy('atleta_list')

    def get_queryset(self):
        return Atleta.objects.filter(cadastrado_por=self.request.user)

# Remoção de inscrições e solicitações de inclusão legadas por equipes


# =====================================================================
# Vistas Adicionais: Avaliação de Delegações & Pré-Súmulas Diárias
# =====================================================================

from django.contrib.auth import get_user_model
from django.views import View
from .models import PreSumula

User = get_user_model()

@method_decorator(user_passes_test(lambda u: u.is_staff), name='dispatch')
class AdminDelegacaoListView(LoginRequiredMixin, ListView):
    """
    Lista todas as delegações inscritas para avaliação da Comissão.
    """
    model = User
    template_name = 'core/admin_delegacoes.html'
    context_object_name = 'delegacoes'

    def get_queryset(self):
        # Retorna todos os usuários com papel REPRESENTANTE, pre-buscando seus atletas
        return User.objects.filter(role='REPRESENTANTE').prefetch_related('atletas').order_by('nome_delegacao')


@user_passes_test(lambda u: u.is_staff)
def avaliar_delegacao(request, pk):
    """
    Delega a aprovação/indeferimento da delegação do Representante como um todo.
    """
    representante = get_object_or_404(User, pk=pk, role='REPRESENTANTE')
    if request.method == 'POST':
        status = request.POST.get('status')
        justificativa = request.POST.get('justificativa', '')
        
        if status in ['deferido', 'indeferido', 'pendente']:
            representante.status_delegacao = status
            representante.justificativa_delegacao = justificativa
            representante.save()
            messages.success(request, f"Delegação de {representante.nome_completo} ({representante.nome_delegacao}) avaliada com sucesso como {representante.get_status_delegacao_display()}!")
            
    return redirect('admin_delegacoes')


@user_passes_test(lambda u: u.is_staff)
def avaliar_atleta(request, pk):
    """
    Avaliação individual de conformidade do Atleta pela Comissão.
    """
    atleta = get_object_or_404(Atleta, pk=pk)
    if request.method == 'POST':
        status = request.POST.get('status')  # 'deferido' ou 'indeferido'
        justificativa = request.POST.get('justificativa', '')
        permite_correcao = request.POST.get('permite_correcao') == 'on' or request.POST.get('permite_correcao') == 'true'

        if status == 'deferido':
            atleta.em_conformidade = True
            atleta.justificativa_inconformidade = ''
            atleta.permite_correcao = False
            atleta.link_correcao = None
        elif status == 'indeferido':
            atleta.em_conformidade = False
            atleta.justificativa_inconformidade = justificativa
            atleta.permite_correcao = permite_correcao
        atleta.save()
        messages.success(request, f"Atleta {atleta.nome_completo} avaliado com sucesso!")
    return redirect(request.META.get('HTTP_REFERER', 'admin_delegacoes'))


class PreSumulaListView(LoginRequiredMixin, ListView):
    """
    Lista os jogos para representantes escalarem jogadores, e exibe as pré-súmulas
    enviadas.
    """
    model = Jogo
    template_name = 'core/presumula_list.html'
    context_object_name = 'jogos'

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Jogo.objects.all().order_by('-data_jogo', '-horario_jogo')
        if user.role == 'REPRESENTANTE' and user.status_delegacao != 'deferido':
            return Jogo.objects.none()
        return Jogo.objects.filter(Q(time_a=user) | Q(time_b=user)).order_by('-data_jogo', '-horario_jogo')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        if user.is_staff:
            from collections import defaultdict
            presumulas = PreSumula.objects.select_related('representante').all()
            by_jogo = defaultdict(list)
            for ps in presumulas:
                by_jogo[ps.jogo_id].append(ps)
            
            for jogo in context['jogos']:
                jogo.todas_presumulas = by_jogo[jogo.id]
        else:
            presumulas = PreSumula.objects.filter(representante=user)
            ps_dict = {ps.jogo_id: ps for ps in presumulas}
            for jogo in context['jogos']:
                jogo.minha_presumula = ps_dict.get(jogo.id)
                
        return context


class PreSumulaCreateView(LoginRequiredMixin, View):
    """
    Cadastro de Pré-Súmula diária para escalar atletas em partidas.
    Disponível apenas para Representantes para jogos de sua delegação.
    """
    def get(self, request):
        if request.user.role == 'REPRESENTANTE' and request.user.status_delegacao != 'deferido':
            messages.error(request, "Acesso Bloqueado: Sua delegação ainda não foi deferida pela Comissão Organizadora. Você precisa ter a delegação aprovada para preencher pré-súmulas.")
            return redirect('dashboard')
            
        jogo_id = request.GET.get('jogo')
        if not jogo_id:
            messages.error(request, "Selecione um jogo para preencher a pré-súmula.")
            return redirect('presumula_list')
        
        jogo = get_object_or_404(Jogo, pk=jogo_id)
        
        # Verifica se o jogo é da delegação do usuário (ou se é staff)
        if not request.user.is_staff and jogo.time_a != request.user and jogo.time_b != request.user:
            messages.error(request, "Você não tem permissão para preencher a pré-súmula para este jogo.")
            return redirect('presumula_list')
            
        # Verifica se já existe pré-súmula cadastrada por este representante para este jogo
        if PreSumula.objects.filter(jogo=jogo, representante=request.user).exists():
            ps = PreSumula.objects.get(jogo=jogo, representante=request.user)
            return redirect('presumula_update', pk=ps.id)
            
        # Filtra os atletas da delegação em conformidade e pelo sexo da categoria
        genero_modalidade = jogo.modalidade.genero
        atletas = Atleta.objects.filter(cadastrado_por=request.user, em_conformidade=True)
        if genero_modalidade == 'M':
            atletas = atletas.filter(genero__in=['M', 'N'])
        elif genero_modalidade == 'F':
            atletas = atletas.filter(genero__in=['F', 'N'])
            
        return render(request, 'core/presumula_form.html', {
            'jogo': jogo,
            'atletas': atletas,
            'is_create': True
        })

    def post(self, request):
        if request.user.role == 'REPRESENTANTE' and request.user.status_delegacao != 'deferido':
            messages.error(request, "Acesso Bloqueado: Sua delegação não está deferida.")
            return redirect('dashboard')

        jogo_id = request.POST.get('jogo_id')
        jogo = get_object_or_404(Jogo, pk=jogo_id)
        
        if not request.user.is_staff and jogo.time_a != request.user and jogo.time_b != request.user:
            messages.error(request, "Acesso negado.")
            return redirect('presumula_list')
            
        if PreSumula.objects.filter(jogo=jogo, representante=request.user).exists():
            messages.error(request, "Você já preencheu a pré-súmula para este jogo.")
            return redirect('presumula_list')
            
        atleta_ids = request.POST.getlist('atletas')
        
        presumula = PreSumula.objects.create(
            jogo=jogo,
            representante=request.user
        )
        
        for atleta_id in atleta_ids:
            numero_camisa = request.POST.get(f'camisa_{atleta_id}')
            if numero_camisa:
                PreSumulaAtleta.objects.create(
                    presumula=presumula,
                    atleta_id=atleta_id,
                    numero_camisa=int(numero_camisa)
                )
                
        messages.success(request, f"Pré-súmula enviada com sucesso para o jogo {jogo}!")
        return redirect('presumula_list')


class PreSumulaUpdateView(LoginRequiredMixin, View):
    """
    Edição de uma pré-súmula de escalação.
    """
    def get(self, request, pk):
        if request.user.role == 'REPRESENTANTE' and request.user.status_delegacao != 'deferido':
            messages.error(request, "Acesso Bloqueado: Sua delegação ainda não foi deferida.")
            return redirect('dashboard')

        presumula = get_object_or_404(PreSumula, pk=pk)
        if not request.user.is_staff and presumula.representante != request.user:
            messages.error(request, "Você não tem permissão para editar esta pré-súmula.")
            return redirect('presumula_list')

        jogo = presumula.jogo
        genero_modalidade = jogo.modalidade.genero
        
        # Filtra os atletas da delegação em conformidade e pelo sexo da categoria
        atletas = Atleta.objects.filter(cadastrado_por=presumula.representante, em_conformidade=True)
        if genero_modalidade == 'M':
            atletas = atletas.filter(genero__in=['M', 'N'])
        elif genero_modalidade == 'F':
            atletas = atletas.filter(genero__in=['F', 'N'])
            
        # Busca atletas escalados para pré-marcar na view e carregar camisa
        escalados_dict = {
            pa.atleta_id: pa.numero_camisa 
            for pa in PreSumulaAtleta.objects.filter(presumula=presumula)
        }
        for atleta in atletas:
            if atleta.id in escalados_dict:
                atleta.is_escalado = True
                atleta.camisa = escalados_dict[atleta.id]
            else:
                atleta.is_escalado = False
                atleta.camisa = ""

        return render(request, 'core/presumula_form.html', {
            'presumula': presumula,
            'jogo': jogo,
            'atletas': atletas,
            'is_create': False
        })

    def post(self, request, pk):
        if request.user.role == 'REPRESENTANTE' and request.user.status_delegacao != 'deferido':
            messages.error(request, "Acesso Bloqueado: Sua delegação não está deferida.")
            return redirect('dashboard')

        presumula = get_object_or_404(PreSumula, pk=pk)
        if not request.user.is_staff and presumula.representante != request.user:
            messages.error(request, "Sem permissão.")
            return redirect('presumula_list')

        atleta_ids = request.POST.getlist('atletas')

        # Limpa escalações antigas
        PreSumulaAtleta.objects.filter(presumula=presumula).delete()
        
        # Cria as novas escalações com os números de camisa
        for atleta_id in atleta_ids:
            numero_camisa = request.POST.get(f'camisa_{atleta_id}')
            if numero_camisa:
                PreSumulaAtleta.objects.create(
                    presumula=presumula,
                    atleta_id=atleta_id,
                    numero_camisa=int(numero_camisa)
                )
        
        messages.success(request, "Pré-súmula atualizada com sucesso!")
        return redirect('presumula_list')


class PreSumulaDetailView(LoginRequiredMixin, DetailView):
    """
    Visualização detalhada da escalação diária (Pré-Súmula).
    """
    model = PreSumula
    template_name = 'core/presumula_detail.html'
    context_object_name = 'presumula'

    def get_queryset(self):
        if self.request.user.is_staff:
            return PreSumula.objects.all()
        return PreSumula.objects.filter(representante=self.request.user)

@method_decorator(user_passes_test(lambda u: u.is_staff), name='dispatch')
class AdminWhitelistView(LoginRequiredMixin, View):
    """
    Lista e gerencia os e-mails autorizados para a Comissão Organizadora (Whitelist).
    """
    def get(self, request):
        whitelist = ComissaoWhitelist.objects.all().order_by('-data_adicao')
        return render(request, 'core/admin_whitelist.html', {'whitelist': whitelist})

    def post(self, request):
        email = request.POST.get('email', '').strip().lower()
        if not email:
            messages.error(request, "O e-mail é obrigatório.")
            return redirect('admin_whitelist')
        
        if ComissaoWhitelist.objects.filter(email__iexact=email).exists():
            messages.warning(request, f"O e-mail {email} já está na whitelist.")
            return redirect('admin_whitelist')
            
        ComissaoWhitelist.objects.create(email=email)
        messages.success(request, f"E-mail {email} autorizado com sucesso!")
        return redirect('admin_whitelist')

@user_passes_test(lambda u: u.is_staff)
def whitelist_delete(request, pk):
    item = get_object_or_404(ComissaoWhitelist, pk=pk)
    email = item.email
    item.delete()
    messages.success(request, f"E-mail {email} removido da whitelist da comissão.")
    return redirect('admin_whitelist')
