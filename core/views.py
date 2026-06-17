from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import login, logout
from django.urls import reverse_lazy
from django.contrib import messages
from .models import Atleta, Modalidade, Equipe, SolicitacaoInclusao
from .forms import RegisterForm, AtletaForm, EquipeForm

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

from django.contrib.auth.models import User
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
            context['total_equipes_global'] = Equipe.objects.count()
            context['total_atletas_global'] = Atleta.objects.count()
            context['total_usuarios'] = User.objects.count()
            context['ultimas_equipes'] = Equipe.objects.all().order_by('-data_inscricao')[:10]
            
            # Estatísticas por Modalidade
            context['stats_modalidade'] = Modalidade.objects.annotate(
                num_equipes=Count('equipes')
            ).order_by('-num_equipes')
            
            # Estatísticas por Campus (Baseado nos Atletas)
            context['stats_campus'] = Atleta.objects.values('campus').annotate(
                total=Count('id')
            ).order_by('-total')
            
            # Estatísticas por Atlética/Usuário
            context['stats_atletica'] = User.objects.filter(equipes_representadas__isnull=False).distinct().annotate(
                num_inscricoes=Count('equipes_representadas')
            ).order_by('-num_inscricoes')
            
            return context
        
        context['is_admin'] = False
        context['total_atletas'] = Atleta.objects.filter(cadastrado_por=user).count()
        context['minhas_equipes'] = Equipe.objects.filter(representante=user)
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
    fields = ['nome', 'limite_minimo_jogadores', 'limite_maximo_jogadores', 'inscricoes_abertas']
    template_name = 'core/modalidade_form.html'
    success_url = reverse_lazy('admin_modalidades')

    def form_valid(self, form):
        messages.success(self.request, "Modalidade criada com sucesso!")
        return super().form_valid(form)

@method_decorator(user_passes_test(lambda u: u.is_staff), name='dispatch')
class ModalidadeUpdateView(LoginRequiredMixin, UpdateView):
    model = Modalidade
    fields = ['nome', 'limite_minimo_jogadores', 'limite_maximo_jogadores', 'inscricoes_abertas']
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

@method_decorator(user_passes_test(lambda u: u.is_staff), name='dispatch')
class AdminEquipeListView(LoginRequiredMixin, ListView):
    model = Equipe
    template_name = 'core/admin_equipes.html'
    context_object_name = 'equipes'
    
    def get_queryset(self):
        queryset = Equipe.objects.all().order_by('-data_inscricao')
        campus = self.request.GET.get('campus')
        modalidade = self.request.GET.get('modalidade')
        status = self.request.GET.get('status')
        
        if campus:
            queryset = queryset.filter(atletas__campus=campus).distinct()
        if modalidade:
            queryset = queryset.filter(modalidade_id=modalidade)
        if status:
            queryset = queryset.filter(status=status)
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['campi_list'] = Atleta.objects.values_list('campus', flat=True).distinct()
        context['modalidades_list'] = Modalidade.objects.all()
        return context

@user_passes_test(lambda u: u.is_staff)
def toggle_modalidade(request, pk):
    modalidade = get_object_or_404(Modalidade, pk=pk)
    modalidade.inscricoes_abertas = not modalidade.inscricoes_abertas
    modalidade.save()
    messages.success(request, f"Status da modalidade {modalidade.nome} alterado!")
    return redirect('admin_modalidades')

class RegulamentoView(TemplateView):
    template_name = 'core/regulamento.html'

@user_passes_test(lambda u: u.is_staff)
def avaliar_equipe(request, pk):
    equipe = get_object_or_404(Equipe, pk=pk)
    if request.method == 'POST':
        novo_status = request.POST.get('status')
        justificativa_equipe = request.POST.get('justificativa')
        inconformes_ids = request.POST.getlist('atletas_inconformes[]')
        
        # Validação de Quórum
        atletas_validos = equipe.atletas.count() - len(inconformes_ids)
        if novo_status == 'aprovado' and atletas_validos < equipe.modalidade.limite_minimo_jogadores:
            messages.error(request, f"Bloqueio: A equipe não pode ser aprovada. Quórum efetivo ({atletas_validos}) menor que o mínimo exigido ({equipe.modalidade.limite_minimo_jogadores}).")
            return redirect('avaliar_equipe', pk=pk)

        # Processar inconformidade de atletas individuais
        for atleta in equipe.atletas.all():
            str_id = str(atleta.id)
            if str_id in inconformes_ids:
                atleta.em_conformidade = False
                atleta.justificativa_inconformidade = request.POST.get(f'justificativa_atleta_{str_id}')
                atleta.permite_correcao = request.POST.get(f'permite_correcao_{str_id}') == 'on'
                # Se a comissão avaliou de novo, podemos limpar o link_correcao antigo para forçar novo envio se necessário,
                # ou manter. Vamos manter para o admin ver, mas se ele marcou permite_correcao, ele espera novo link.
                atleta.save()
            else:
                # Se o admin desmarcou a irregularidade (talvez após ver a correção), o atleta volta a ficar ok
                if not atleta.em_conformidade:
                    atleta.em_conformidade = True
                    atleta.justificativa_inconformidade = ''
                    atleta.permite_correcao = False
                    atleta.link_correcao = None
                    atleta.save()

        if novo_status in ['aprovado', 'rejeitado']:
            equipe.status = novo_status
            equipe.justificativa = justificativa_equipe
            equipe.save()
            
            if novo_status == 'aprovado':
                messages.success(request, f"Equipe aprovada! Quórum efetivo: {atletas_validos} de {equipe.modalidade.limite_minimo_jogadores}.")
            else:
                messages.success(request, f"Equipe rejeitada com sucesso.")
            return redirect('admin_equipes')
            
    return render(request, 'core/avaliar_equipe.html', {'equipe': equipe})

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
    return redirect(request.META.get('HTTP_REFERER', 'admin_equipes'))

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
        is_egressos = request.POST.getlist('is_egresso[]')
        links_egressos = request.POST.getlist('link_egresso[]')

        atletas_criados = 0
        for i in range(len(nomes)):
            if nomes[i].strip():
                is_egr = (is_egressos[i] == '1') if i < len(is_egressos) else False
                link_egr = links_egressos[i] if i < len(links_egressos) else ''
                
                Atleta.objects.create(
                    nome_completo=nomes[i],
                    cpf=cpfs[i] if i < len(cpfs) else '',
                    email=emails[i],
                    matricula=matriculas[i],
                    curso=cursos[i],
                    campus=campi[i],
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

# Modalidades e Equipes
class ModalidadeListView(LoginRequiredMixin, ListView):
    model = Modalidade
    template_name = 'core/modalidade_list.html'
    context_object_name = 'modalidades'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['modalidades_inscritas_ids'] = list(Equipe.objects.filter(representante=self.request.user).values_list('modalidade_id', flat=True))
        return context

class EquipeCreateView(LoginRequiredMixin, CreateView):
    model = Equipe
    form_class = EquipeForm
    template_name = 'core/equipe_form.html'
    success_url = reverse_lazy('dashboard')

    def dispatch(self, request, *args, **kwargs):
        modalidade_id = self.kwargs.get('modalidade_id')
        if Equipe.objects.filter(representante=request.user, modalidade_id=modalidade_id).exists():
            messages.error(request, "Sua atlética já possui uma inscrição para esta modalidade. Não é possível recadastrar.")
            return redirect('modalidade_list')
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['modalidade'] = get_object_or_404(Modalidade, pk=self.kwargs['modalidade_id'])
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['modalidade'] = get_object_or_404(Modalidade, pk=self.kwargs['modalidade_id'])
        return context

    def form_valid(self, form):
        form.instance.representante = self.request.user
        form.instance.modalidade = get_object_or_404(Modalidade, pk=self.kwargs['modalidade_id'])
        if not form.instance.modalidade.inscricoes_abertas:
            messages.error(self.request, "As inscrições para esta modalidade estão encerradas.")
            return self.form_invalid(form)
        
        response = super().form_valid(form)
        messages.success(self.request, f"Equipe inscrita com sucesso em {form.instance.modalidade.nome}!")
        return response

class EquipeUpdateView(LoginRequiredMixin, UpdateView):
    model = Equipe
    form_class = EquipeForm
    template_name = 'core/equipe_form.html'
    success_url = reverse_lazy('dashboard')

    def dispatch(self, request, *args, **kwargs):
        equipe = self.get_object()
        if equipe.status in ['pendente', 'aprovado']:
            messages.error(request, "Você não pode editar uma equipe que está em análise ou já foi aprovada.")
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['modalidade'] = self.object.modalidade
        return kwargs

    def get_queryset(self):
        return Equipe.objects.filter(representante=self.request.user)

class EquipeDetailView(LoginRequiredMixin, DetailView):
    model = Equipe
    template_name = 'core/equipe_detail.html'
    context_object_name = 'equipe'

    def get_queryset(self):
        # Admin vê qualquer equipe, usuário comum vê apenas a sua
        if self.request.user.is_staff:
            return Equipe.objects.all()
        return Equipe.objects.filter(representante=self.request.user)

class EquipeDeleteView(LoginRequiredMixin, DeleteView):
    model = Equipe
    template_name = 'core/confirm_delete.html'
    success_url = reverse_lazy('dashboard')

    def get_queryset(self):
        return Equipe.objects.filter(representante=self.request.user)

from .forms import SolicitacaoInclusaoForm

class SolicitacaoInclusaoCreateView(LoginRequiredMixin, CreateView):
    model = SolicitacaoInclusao
    form_class = SolicitacaoInclusaoForm
    template_name = 'core/solicitacao_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.equipe = get_object_or_404(Equipe, pk=self.kwargs['equipe_id'], representante=request.user)
        if self.equipe.status != 'aprovado':
            messages.error(request, "Você só pode solicitar inclusão de atletas em equipes já aprovadas.")
            return redirect('equipe_detail', pk=self.equipe.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['equipe'] = self.equipe
        return kwargs

    def form_valid(self, form):
        form.instance.equipe = self.equipe
        messages.success(self.request, "Solicitação de inclusão enviada para análise da comissão.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('equipe_detail', pk=self.equipe.pk)

@user_passes_test(lambda u: u.is_staff)
def avaliar_solicitacao(request, pk):
    solicitacao = get_object_or_404(SolicitacaoInclusao, pk=pk)
    if request.method == 'POST':
        novo_status = request.POST.get('status')
        justificativa = request.POST.get('justificativa', '')
        
        if novo_status in ['aprovado', 'rejeitado']:
            solicitacao.status = novo_status
            solicitacao.justificativa = justificativa
            solicitacao.save()
            
            if novo_status == 'aprovado':
                solicitacao.equipe.atletas.add(solicitacao.atleta)
                
            messages.success(request, f"Solicitação de {solicitacao.atleta.nome_completo} avaliada!")
            
    return redirect('avaliar_equipe', pk=solicitacao.equipe.pk)
