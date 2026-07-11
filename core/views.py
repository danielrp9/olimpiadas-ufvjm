from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import login, logout
from django.urls import reverse_lazy
from django.contrib import messages
from .models import Atleta, Modalidade, Jogo, PreSumula, PreSumulaAtleta, Inscricao, InscricaoModalidade, Recurso, RecursoMensagem, Notificacao
from .forms import RegisterForm, AtletaForm, JogoForm, ModalidadeForm
from users.models import ComissaoWhitelist, MembroDelegacao

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
        context['unread_notifications'] = Notificacao.objects.filter(usuario=user, lida=False)
        
        if user.is_comissao:
            context['is_admin'] = True
            context['total_atletas_global'] = Atleta.objects.count()
            context['total_usuarios'] = User.objects.filter(role='REPRESENTANTE', parent_delegate__isnull=True, inscricao__isnull=False).count()
            context['total_presumulas_global'] = PreSumula.objects.count()
            
            # Analytics data for the Commission
            from core.models import Campus
            campi_list = Campus.objects.all().order_by('nome')
            
            campi_stats = []
            total_servidores_global = Atleta.objects.filter(tipo_atleta='servidor').count()
            total_estudantes_global = Atleta.objects.filter(tipo_atleta='estudante').count()
            total_inscritos_global = Atleta.objects.count()
            
            for campus in campi_list:
                # Count distinct delegations with athletes in this campus
                delegacoes_count = User.objects.filter(
                    role='REPRESENTANTE',
                    parent_delegate__isnull=True,
                    inscricao__isnull=False,
                    atletas__campus=campus
                ).distinct().count()
                
                atletas_count = Atleta.objects.filter(campus=campus, tipo_atleta='estudante').count()
                servidores_count = Atleta.objects.filter(campus=campus, tipo_atleta='servidor').count()
                total_membros = atletas_count + servidores_count
                
                campi_stats.append({
                    'nome': campus.nome,
                    'delegacoes': delegacoes_count,
                    'atletas': atletas_count,
                    'servidores': servidores_count,
                    'total_membros': total_membros,
                })
                
            max_members = 0
            for stat in campi_stats:
                total_m = stat['total_membros']
                if total_m > max_members:
                    max_members = total_m
            
            context['campi_stats'] = campi_stats
            context['total_servidores_global'] = total_servidores_global
            context['total_estudantes_global'] = total_estudantes_global
            context['total_inscritos_global'] = total_inscritos_global
            context['max_members'] = max_members
                
            return context
        
        delegacao = user.delegacao_ativa
        context['is_admin'] = False
        context['total_atletas'] = Atleta.objects.filter(cadastrado_por=delegacao).count()
        
        presumulas = PreSumula.objects.filter(representante=delegacao)
        context['total_presumulas'] = presumulas.count()
        ps_dict = {ps.jogo_id: ps for ps in presumulas}
        
        # Jogos ativos (não finalizados e sem WO)
        jogos_ativos_raw = Jogo.objects.filter(
            Q(time_a=delegacao) | Q(time_b=delegacao),
            finalizado=False
        ).order_by('-data_jogo', '-horario_jogo', '-id')
        
        jogos_ativos = []
        jogos_wo = []
        for jogo in jogos_ativos_raw:
            jogo.minha_presumula = ps_dict.get(jogo.id)
            if jogo.is_finalizado_por_wo:
                jogos_wo.append(jogo)
            else:
                jogos_ativos.append(jogo)
        context['jogos_ativos'] = jogos_ativos
        
        # Jogos encerrados (histórico)
        jogos_encerrados_raw = Jogo.objects.filter(
            Q(time_a=delegacao) | Q(time_b=delegacao),
            finalizado=True
        ).order_by('-data_jogo', '-horario_jogo', '-id')
        
        recursos_delegacao = {r.jogo_id: r for r in Recurso.objects.filter(requerente=delegacao)}
        
        jogos_encerrados = list(jogos_encerrados_raw)
        for jogo in jogos_encerrados:
            jogo.minha_presumula = ps_dict.get(jogo.id)
            jogo.meu_recurso = recursos_delegacao.get(jogo.id)
            
        for jogo in jogos_wo:
            jogo.meu_recurso = recursos_delegacao.get(jogo.id)
            
        jogos_encerrados.extend(jogos_wo)
        import datetime
        jogos_encerrados.sort(key=lambda j: (j.data_jogo or datetime.date.min, j.horario_jogo or datetime.time.min, j.id), reverse=True)
        context['jogos_encerrados'] = jogos_encerrados
        
        from django.utils import timezone
        context['modalidades_abertas'] = Modalidade.objects.filter(inscricoes_abertas=True).filter(
            Q(data_publicacao__isnull=True) | Q(data_publicacao__lte=timezone.now())
        )
        
        context['inscricao'] = getattr(delegacao, 'inscricao', None)
        return context

@method_decorator(user_passes_test(lambda u: u.is_staff), name='dispatch')
class AdminModalidadeListView(LoginRequiredMixin, ListView):
    model = Modalidade
    template_name = 'core/admin_modalidades.html'
    context_object_name = 'modalidades'

@method_decorator(user_passes_test(lambda u: u.is_staff), name='dispatch')
class ModalidadeCreateView(LoginRequiredMixin, CreateView):
    model = Modalidade
    form_class = ModalidadeForm
    template_name = 'core/modalidade_form.html'
    success_url = reverse_lazy('admin_modalidades')

    def form_valid(self, form):
        messages.success(self.request, "Modalidade criada com sucesso!")
        return super().form_valid(form)

@method_decorator(user_passes_test(lambda u: u.is_staff), name='dispatch')
class ModalidadeUpdateView(LoginRequiredMixin, UpdateView):
    model = Modalidade
    form_class = ModalidadeForm
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

@login_required
@user_passes_test(lambda u: u.is_staff)
def finalizar_jogo(request, pk):
    if request.method == 'POST':
        jogo = get_object_or_404(Jogo, pk=pk)
        jogo.finalizado = True
        from django.utils import timezone
        jogo.data_hora_fim = timezone.now()
        jogo.save()
        messages.success(request, f"O jogo {jogo.modalidade.nome} ({jogo.time_a.nome_delegacao or jogo.time_a.email} vs {jogo.time_b.nome_delegacao or jogo.time_b.email}) foi encerrado com sucesso!")
    return redirect('presumula_list')



# Remoção de avaliar_equipe de inscrições legadas

@login_required
def enviar_correcao_atleta(request, pk):
    atleta = get_object_or_404(Atleta, pk=pk, cadastrado_por=request.user.delegacao_ativa)
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
    atleta.status_avaliacao = 'deferido'
    atleta.save()
    messages.success(request, f"Atleta {atleta.nome_completo} restaurado para conformidade!")
    return redirect(request.META.get('HTTP_REFERER', 'admin_delegacoes'))

# Atletas Views
class AtletaListView(LoginRequiredMixin, ListView):
    model = Atleta
    template_name = 'core/atleta_list.html'
    context_object_name = 'atletas'

    def get_queryset(self):
        return Atleta.objects.filter(cadastrado_por=self.request.user.delegacao_ativa)

class AtletaBulkCreateView(LoginRequiredMixin, TemplateView):
    template_name = 'core/atleta_bulk_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import Campus
        context['campi'] = Campus.objects.all().order_by('nome')
        return context

    def post(self, request, *args, **kwargs):
        nomes = request.POST.getlist('nome[]')
        cpfs = request.POST.getlist('cpf[]')
        emails = request.POST.getlist('email[]')
        matriculas = request.POST.getlist('matricula[]')
        cursos = request.POST.getlist('curso[]')
        campi = request.POST.getlist('campus[]')
        generos = request.POST.getlist('genero[]')
        tipo_atletas = request.POST.getlist('tipo_atleta[]')
        is_egressos = request.POST.getlist('is_egresso[]')
        links_documentos = request.POST.getlist('link_documento[]')

        atletas_criados = 0
        for i in range(len(nomes)):
            if nomes[i].strip():
                is_egr = (is_egressos[i] == '1') if i < len(is_egressos) else False
                gen = generos[i] if i < len(generos) else 'M'
                tipo_atl = tipo_atletas[i] if i < len(tipo_atletas) else 'estudante'
                link_doc = links_documentos[i] if i < len(links_documentos) else ''
                
                # Fetch selected campus ID
                c_id = int(campi[i]) if i < len(campi) and campi[i].isdigit() else None
                
                Atleta.objects.create(
                    nome_completo=nomes[i],
                    cpf=cpfs[i] if i < len(cpfs) else '',
                    email=emails[i],
                    matricula=matriculas[i],
                    curso=cursos[i],
                    campus_id=c_id,
                    genero=gen,
                    tipo_atleta=tipo_atl,
                    is_egresso=is_egr,
                    link_documento_egresso='',
                    link_documento=link_doc,
                    cadastrado_por=request.user.delegacao_ativa
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
        return Atleta.objects.filter(cadastrado_por=self.request.user.delegacao_ativa)

class AtletaDeleteView(LoginRequiredMixin, DeleteView):
    model = Atleta
    template_name = 'core/confirm_delete.html'
    success_url = reverse_lazy('atleta_list')

    def get_queryset(self):
        return Atleta.objects.filter(cadastrado_por=self.request.user.delegacao_ativa)

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
        # Retorna apenas os representantes que de fato realizaram uma inscrição
        return User.objects.filter(role='REPRESENTANTE', parent_delegate__isnull=True, inscricao__isnull=False).prefetch_related(
            'atletas', 
            'inscricao__modalidades__modalidade', 
            'inscricao__modalidades__atletas'
        ).order_by('nome_delegacao')


@user_passes_test(lambda u: u.is_staff)
def avaliar_delegacao(request, pk):
    """
    Delega a aprovação/indeferimento da delegação do Representante como um todo.
    """
    representante = get_object_or_404(User, pk=pk, role='REPRESENTANTE')
    inscricao = get_object_or_404(Inscricao, delegacao=representante)
    if request.method == 'POST':
        status = request.POST.get('status')
        justificativa = request.POST.get('justificativa', '')
        
        if status in ['deferido', 'indeferido', 'pendente']:
            if status != 'indeferido':
                justificativa = ''
            
            # Salva o status na Inscrição
            inscricao.status = status
            inscricao.justificativa = justificativa
            inscricao.save()
            
            # Mantém em sincronia com o modelo User legada
            representante.status_delegacao = status
            representante.justificativa_delegacao = justificativa
            representante.save()
            
            # Notifica os representantes e membros da delegação
            if status == 'deferido':
                msg_notif = "Sua inscrição foi avaliada e DEFERIDA (aprovada) pela comissão organizadora."
            elif status == 'indeferido':
                msg_notif = f"Sua inscrição foi avaliada e INDEFERIDA (recusada) pela comissão organizadora. Motivo: {justificativa}"
            else:
                msg_notif = "Sua inscrição foi alterada para PENDENTE de análise."
                
            usuarios_delegacao = User.objects.filter(Q(id=representante.id) | Q(parent_delegate=representante))
            for usr in usuarios_delegacao:
                Notificacao.objects.create(
                    usuario=usr,
                    mensagem=msg_notif,
                    link='/inscricao/detalhe/'
                )
            
            messages.success(request, f"Delegação de {representante.nome_completo} ({representante.nome_delegacao}) avaliada com sucesso como {inscricao.get_status_display()}!")
            
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
            atleta.status_avaliacao = 'deferido'
        elif status == 'indeferido':
            atleta.em_conformidade = False
            atleta.justificativa_inconformidade = justificativa
            atleta.permite_correcao = permite_correcao
            atleta.status_avaliacao = 'indeferido'
        atleta.save()
        messages.success(request, f"Atleta {atleta.nome_completo} avaliado com sucesso!")
    return redirect(request.META.get('HTTP_REFERER', 'admin_delegacoes'))


@login_required
def enviar_comprovante_pagamento(request):
    """
    Permite ao delegado enviar ou atualizar o comprovante de pagamento único da delegação.
    """
    if request.method == 'POST':
        link = request.POST.get('link_comprovante_pagamento', '').strip()
        delegado = request.user.delegacao_ativa
        delegado.link_comprovante_pagamento = link
        delegado.status_pagamento = 'nao_avaliado'
        delegado.justificativa_pagamento = ''
        delegado.save()
        messages.success(request, "Comprovante de pagamento único enviado com sucesso!")
    return redirect(request.META.get('HTTP_REFERER', 'atleta_list'))


@user_passes_test(lambda u: u.is_staff)
def avaliar_pagamento(request, pk):
    """
    Permite à comissão deferir ou indeferir o comprovante de pagamento único da delegação.
    """
    delegado = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        status = request.POST.get('status')
        justificativa = request.POST.get('justificativa', '')

        if status == 'deferido':
            delegado.status_pagamento = 'deferido'
            delegado.justificativa_pagamento = ''
        elif status == 'indeferido':
            delegado.status_pagamento = 'indeferido'
            delegado.justificativa_pagamento = justificativa
        delegado.save()
        messages.success(request, f"Pagamento da delegação {delegado.nome_delegacao} avaliado com sucesso!")
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
        
        # Captura parâmetros de filtros
        self.modalidade_id = self.request.GET.get('modalidade')
        self.delegacao_id = self.request.GET.get('delegacao')
        self.data_jogo = self.request.GET.get('data')
        
        if user.is_staff:
            qs = Jogo.objects.all()
        else:
            delegacao = user.delegacao_ativa
            if delegacao.role == 'REPRESENTANTE' and delegacao.status_delegacao != 'deferido':
                return Jogo.objects.none()
            qs = Jogo.objects.filter(Q(time_a=delegacao) | Q(time_b=delegacao))
            
        # Filtros
        if self.modalidade_id:
            qs = qs.filter(modalidade_id=self.modalidade_id)
        if self.data_jogo:
            qs = qs.filter(data_jogo=self.data_jogo)
        if self.delegacao_id:
            qs = qs.filter(Q(time_a_id=self.delegacao_id) | Q(time_b_id=self.delegacao_id))
            
        return qs.order_by('-data_jogo', '-horario_jogo', '-id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Filtros ativos count
        modalidade_id = self.request.GET.get('modalidade')
        delegacao_id = self.request.GET.get('delegacao')
        data_jogo = self.request.GET.get('data')
        
        filtros_ativos = 0
        if modalidade_id:
            filtros_ativos += 1
        if delegacao_id:
            filtros_ativos += 1
        if data_jogo:
            filtros_ativos += 1
            
        context['filtros_ativos'] = filtros_ativos
        context['selected_modalidade'] = modalidade_id
        context['selected_delegacao'] = delegacao_id
        context['selected_data'] = data_jogo
        
        # Listas para o dropdown de filtros
        context['modalidades'] = Modalidade.objects.all().order_by('nome')
        
        from django.contrib.auth import get_user_model
        User = get_user_model()
        context['delegacoes_list'] = User.objects.filter(role='REPRESENTANTE', parent_delegate__isnull=True).order_by('nome_delegacao')
        
        if user.is_staff:
            from collections import defaultdict
            presumulas = PreSumula.objects.select_related('representante').all()
            by_jogo = defaultdict(list)
            for ps in presumulas:
                by_jogo[ps.jogo_id].append(ps)
            
            for jogo in context['jogos']:
                jogo.todas_presumulas = by_jogo[jogo.id]
                jogo.presumula_a = next((ps for ps in by_jogo[jogo.id] if ps.representante_id == jogo.time_a_id), None)
                jogo.presumula_b = next((ps for ps in by_jogo[jogo.id] if ps.representante_id == jogo.time_b_id), None)
        else:
            delegacao = user.delegacao_ativa
            presumulas = PreSumula.objects.filter(representante=delegacao)
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
        delegacao = request.user.delegacao_ativa
        if delegacao.role == 'REPRESENTANTE' and delegacao.status_delegacao != 'deferido':
            messages.error(request, "Acesso Bloqueado: Sua delegação ainda não foi deferida pela Comissão Organizadora. Você precisa ter a delegação aprovada para preencher pré-súmulas.")
            return redirect('dashboard')
            
        jogo_id = request.GET.get('jogo')
        if not jogo_id:
            messages.error(request, "Selecione um jogo para preencher a pré-súmula.")
            return redirect('presumula_list')
        
        jogo = get_object_or_404(Jogo, pk=jogo_id)
        
        # Verifica se o jogo é da delegação do usuário (ou se é staff)
        if not request.user.is_staff and jogo.time_a != delegacao and jogo.time_b != delegacao:
            messages.error(request, "Você não tem permissão para preencher a pré-súmula para este jogo.")
            return redirect('presumula_list')

        # Verifica limite de 1h antes do jogo
        if not request.user.is_staff and jogo.is_presumula_deadline_passed:
            messages.error(request, "Prazo encerrado: A pré-súmula deve ser preenchida em até 1h antes do jogo. WO foi aplicado.")
            return redirect('presumula_list')
            
        # Verifica se já existe pré-súmula cadastrada por este representante para este jogo
        if PreSumula.objects.filter(jogo=jogo, representante=delegacao).exists():
            ps = PreSumula.objects.get(jogo=jogo, representante=delegacao)
            return redirect('presumula_update', pk=ps.id)
            
        # Filtra os atletas da delegação em conformidade e pelo sexo da categoria
        genero_modalidade = jogo.modalidade.genero
        atletas = Atleta.objects.filter(cadastrado_por=delegacao, em_conformidade=True)
        if genero_modalidade == 'M':
            atletas = atletas.filter(genero__in=['M', 'N'])
        elif genero_modalidade == 'F':
            atletas = atletas.filter(genero__in=['F', 'N'])
            
        return render(request, 'core/presumula_form.html', {
            'jogo': jogo,
            'atletas': atletas,
            'is_create': True,
            'presumula': None,
            'tecnico': ''
        })

    def post(self, request):
        delegacao = request.user.delegacao_ativa
        if delegacao.role == 'REPRESENTANTE' and delegacao.status_delegacao != 'deferido':
            messages.error(request, "Acesso Bloqueado: Sua delegação não está deferida.")
            return redirect('dashboard')

        jogo_id = request.POST.get('jogo_id')
        jogo = get_object_or_404(Jogo, pk=jogo_id)
        
        if not request.user.is_staff and jogo.time_a != delegacao and jogo.time_b != delegacao:
            messages.error(request, "Acesso negado.")
            return redirect('presumula_list')

        # Verifica limite de 1h antes do jogo
        if not request.user.is_staff and jogo.is_presumula_deadline_passed:
            messages.error(request, "Prazo encerrado: A pré-súmula deve ser preenchida em até 1h antes do jogo. WO foi aplicado.")
            return redirect('presumula_list')
            
        if PreSumula.objects.filter(jogo=jogo, representante=delegacao).exists():
            messages.error(request, "Você já preencheu a pré-súmula para este jogo.")
            return redirect('presumula_list')
            
        atleta_ids = request.POST.getlist('atletas')
        tecnico = request.POST.get('tecnico', '').strip()

        # Validar número de atletas contra limites da modalidade
        min_atletas = jogo.modalidade.limite_minimo_jogadores
        max_atletas = jogo.modalidade.limite_maximo_jogadores
        num_selecionados = len(atleta_ids)

        if num_selecionados < min_atletas or num_selecionados > max_atletas:
            limit_msg = f"no mínimo {min_atletas}" if num_selecionados < min_atletas else f"no máximo {max_atletas}"
            messages.error(request, f"Erro: A escalação deve conter {limit_msg} atleta(s) para a modalidade {jogo.modalidade.nome}. (Selecionados: {num_selecionados})")
            
            genero_modalidade = jogo.modalidade.genero
            atletas = Atleta.objects.filter(cadastrado_por=delegacao, em_conformidade=True)
            if genero_modalidade == 'M':
                atletas = atletas.filter(genero__in=['M', 'N'])
            elif genero_modalidade == 'F':
                atletas = atletas.filter(genero__in=['F', 'N'])
                
            for a in atletas:
                a.is_escalado = str(a.id) in atleta_ids
                a.camisa = request.POST.get(f'camisa_{a.id}', '')
                
            return render(request, 'core/presumula_form.html', {
                'jogo': jogo,
                'atletas': atletas,
                'is_create': True,
                'tecnico': tecnico
            })

        presumula = PreSumula.objects.create(
            jogo=jogo,
            representante=delegacao,
            tecnico=tecnico
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
        delegacao = request.user.delegacao_ativa
        if delegacao.role == 'REPRESENTANTE' and delegacao.status_delegacao != 'deferido':
            messages.error(request, "Acesso Bloqueado: Sua delegação ainda não foi deferida.")
            return redirect('dashboard')

        presumula = get_object_or_404(PreSumula, pk=pk)
        if not request.user.is_staff and presumula.representante != delegacao:
            messages.error(request, "Você não tem permissão para editar esta pré-súmula.")
            return redirect('presumula_list')

        # Verifica limite de 1h antes do jogo
        if not request.user.is_staff and presumula.jogo.is_presumula_deadline_passed:
            messages.error(request, "Prazo encerrado: A pré-súmula não pode mais ser editada (limite de 1h antes do jogo).")
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
            'is_create': False,
            'tecnico': presumula.tecnico
        })

    def post(self, request, pk):
        delegacao = request.user.delegacao_ativa
        if delegacao.role == 'REPRESENTANTE' and delegacao.status_delegacao != 'deferido':
            messages.error(request, "Acesso Bloqueado: Sua delegação não está deferida.")
            return redirect('dashboard')

        presumula = get_object_or_404(PreSumula, pk=pk)
        if not request.user.is_staff and presumula.representante != delegacao:
            messages.error(request, "Sem permissão.")
            return redirect('presumula_list')

        # Verifica limite de 1h antes do jogo
        if not request.user.is_staff and presumula.jogo.is_presumula_deadline_passed:
            messages.error(request, "Prazo encerrado: A pré-súmula não pode mais ser editada (limite de 1h antes do jogo).")
            return redirect('presumula_list')

        atleta_ids = request.POST.getlist('atletas')
        tecnico = request.POST.get('tecnico', '').strip()

        # Validar número de atletas contra limites da modalidade
        min_atletas = presumula.jogo.modalidade.limite_minimo_jogadores
        max_atletas = presumula.jogo.modalidade.limite_maximo_jogadores
        num_selecionados = len(atleta_ids)

        if num_selecionados < min_atletas or num_selecionados > max_atletas:
            limit_msg = f"no mínimo {min_atletas}" if num_selecionados < min_atletas else f"no máximo {max_atletas}"
            messages.error(request, f"Erro: A escalação deve conter {limit_msg} atleta(s) para a modalidade {presumula.jogo.modalidade.nome}. (Selecionados: {num_selecionados})")
            
            jogo = presumula.jogo
            genero_modalidade = jogo.modalidade.genero
            atletas = Atleta.objects.filter(cadastrado_por=presumula.representante, em_conformidade=True)
            if genero_modalidade == 'M':
                atletas = atletas.filter(genero__in=['M', 'N'])
            elif genero_modalidade == 'F':
                atletas = atletas.filter(genero__in=['F', 'N'])
                
            for a in atletas:
                a.is_escalado = str(a.id) in atleta_ids
                a.camisa = request.POST.get(f'camisa_{a.id}', '')
                
            return render(request, 'core/presumula_form.html', {
                'presumula': presumula,
                'jogo': jogo,
                'atletas': atletas,
                'is_create': False,
                'tecnico': tecnico
            })

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

        presumula.tecnico = tecnico
        presumula.save()
        
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
        return PreSumula.objects.filter(representante=self.request.user.delegacao_ativa)

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


@login_required
def inscricao_passo1(request):
    if request.user.is_comissao:
        return redirect('dashboard')
    delegacao = request.user.delegacao_ativa
    inscricao = getattr(delegacao, 'inscricao', None)
    if inscricao:
        return redirect('inscricao_detail')
        
    from django.utils import timezone
    modalidades = Modalidade.objects.filter(inscricoes_abertas=True).filter(
        Q(data_publicacao__isnull=True) | Q(data_publicacao__lte=timezone.now())
    )
    
    if request.method == 'POST':
        selected_modalidades = request.POST.getlist('modalidades')
        if not selected_modalidades:
            messages.error(request, "Por favor, selecione ao menos uma modalidade para se inscrever.")
            return redirect('inscricao_passo1')
            
        request.session['inscricao_modalidades_ids'] = [int(mid) for mid in selected_modalidades]
        return redirect('inscricao_passo2')
        
    return render(request, 'core/inscricao_passo1.html', {'modalidades': modalidades})


@login_required
def inscricao_passo2(request):
    if request.user.is_comissao:
        return redirect('dashboard')
    delegacao = request.user.delegacao_ativa
    inscricao = getattr(delegacao, 'inscricao', None)
    if inscricao:
        return redirect('inscricao_detail')
        
    modalidades_ids = request.session.get('inscricao_modalidades_ids', [])
    if not modalidades_ids:
        messages.error(request, "Sua sessão expirou ou você não selecionou nenhuma modalidade. Por favor, reinicie o processo.")
        return redirect('inscricao_passo1')
        
    modalidades = Modalidade.objects.filter(id__in=modalidades_ids)
    atletas = Atleta.objects.filter(cadastrado_por=delegacao)
    
    if not atletas.exists():
        messages.warning(request, "Você precisa cadastrar seus atletas no sistema antes de prosseguir com a inscrição nas modalidades.")
        return redirect('atleta_list')
        
    if request.method == 'POST':
        atleta_ids = request.POST.getlist('atletas')
        selected_atletas = Atleta.objects.filter(id__in=[int(aid) for aid in atleta_ids], cadastrado_por=delegacao)
        
        if not selected_atletas.exists():
            messages.error(request, "Por favor, selecione ao menos um atleta para a inscrição.")
            return render(request, 'core/inscricao_passo2.html', {
                'modalidades': modalidades,
                'atletas': atletas,
                'selected_data': atleta_ids
            })
            
        inscricao, created = Inscricao.objects.get_or_create(
            delegacao=delegacao,
            defaults={'status': 'pendente'}
        )
        
        inscricao.modalidades.all().delete()
        
        for mod in modalidades:
            insc_mod = InscricaoModalidade.objects.create(inscricao=inscricao, modalidade=mod)
            insc_mod.atletas.set(selected_atletas)
            
        delegacao.status_delegacao = 'pendente'
        delegacao.justificativa_delegacao = ''
        delegacao.save()
        
        # Notifica a comissão organizadora de que há uma nova inscrição
        comissao = User.objects.filter(role='COMISSAO')
        for admin in comissao:
            Notificacao.objects.create(
                usuario=admin,
                mensagem=f"Nova inscrição pendente de avaliação da delegação {delegacao.nome_delegacao or delegacao.email}.",
                link='/comissao/delegacoes/'
            )
        
        if 'inscricao_modalidades_ids' in request.session:
            del request.session['inscricao_modalidades_ids']
            
        messages.success(request, "Inscrição enviada com sucesso! A Comissão Organizadora fará a avaliação.")
        return redirect('inscricao_detail')
        
    return render(request, 'core/inscricao_passo2.html', {
        'modalidades': modalidades,
        'atletas': atletas
    })


@login_required
def inscricao_detail(request):
    if request.user.is_comissao:
        return redirect('dashboard')
        
    delegacao = request.user.delegacao_ativa
    inscricao = getattr(delegacao, 'inscricao', None)
    if not inscricao:
        return redirect('inscricao_passo1')
        
    modalidades_inscritas = inscricao.modalidades.all().select_related('modalidade')
    
    return render(request, 'core/inscricao_detail.html', {
        'inscricao': inscricao,
        'modalidades_inscritas': modalidades_inscritas,
        'atletas_inscritos': inscricao.atletas_inscritos
    })


@login_required
def refazer_inscricao(request):
    if request.user.is_comissao:
        return redirect('dashboard')
        
    delegacao = request.user.delegacao_ativa
    inscricao = getattr(delegacao, 'inscricao', None)
    if inscricao:
        if inscricao.status == 'pendente':
            return render(request, 'core/inscricao_fila_espera.html')
        elif inscricao.status == 'indeferido':
            inscricao.delete()
            delegacao.status_delegacao = 'pendente'
            delegacao.save()
            messages.info(request, "Sua inscrição anterior foi cancelada. Você pode iniciar uma nova inscrição agora.")
            return redirect('inscricao_passo1')
        else:
            messages.warning(request, "Sua inscrição já foi deferida e não pode ser alterada.")
            return redirect('inscricao_detail')
            
    return redirect('inscricao_passo1')


import os
from django.conf import settings
from django.http import HttpResponse

def react_app(request, path=''):
    dist_path = os.path.join(settings.BASE_DIR, 'static', 'react', 'dist', 'index.html')
    if not os.path.exists(dist_path):
        return HttpResponse(
            "<html><body style='font-family: sans-serif; background: #0f172a; color: #f1f5f9; padding: 2rem;'>"
            "<h2 style='color: #6366f1;'>Interface React não compilada no Django!</h2>"
            "<p>Para inicializar e rodar o React integrado ao Django, você precisa:</p>"
            "<ol>"
            "<li>Entrar no diretório do front-end: <code>cd frontend</code></li>"
            "<li>Gerar o build de produção: <code>npm run build</code></li>"
            "</ol>"
            "<p>Isso criará a pasta <code>static/react/dist/</code> com os arquivos corretos. "
            "Depois, basta recarregar esta página.</p>"
            "<p><i>Dica de Desenvolvimento:</i> Você também pode rodar o React no servidor dinâmico do Vite (porta 5173) executando <code>npm run dev</code> dentro da pasta <code>frontend</code>.</p>"
            "</body></html>",
            status=404
        )
    with open(dist_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    return HttpResponse(html_content)


class MembrosDelegacaoView(LoginRequiredMixin, View):
    """
    Lista e gerencia os membros (co-delegados) autorizados pelo delegado principal.
    Disponível apenas para delegados representantes principais (sem parent_delegate).
    """
    def get(self, request):
        if request.user.role != 'REPRESENTANTE' or request.user.parent_delegate is not None:
            messages.error(request, "Acesso negado: Apenas delegados representantes principais podem gerenciar membros autorizados.")
            return redirect('dashboard')
            
        membros = MembroDelegacao.objects.filter(delegado_principal=request.user).order_by('-data_adicao')
        return render(request, 'core/membros_delegacao.html', {'membros': membros})

    def post(self, request):
        if request.user.role != 'REPRESENTANTE' or request.user.parent_delegate is not None:
            messages.error(request, "Acesso negado.")
            return redirect('dashboard')
            
        email = request.POST.get('email', '').strip().lower()
        if not email:
            messages.error(request, "O e-mail é obrigatório.")
            return redirect('membros_delegacao')
            
        if email == request.user.email:
            messages.warning(request, "Você não precisa autorizar o seu próprio e-mail.")
            return redirect('membros_delegacao')
            
        if MembroDelegacao.objects.filter(delegado_principal=request.user, email__iexact=email).exists():
            messages.warning(request, f"O e-mail {email} já está autorizado na sua delegação.")
            return redirect('membros_delegacao')
            
        MembroDelegacao.objects.create(delegado_principal=request.user, email=email)
        messages.success(request, f"E-mail {email} autorizado com sucesso para acessar sua delegação!")
        return redirect('membros_delegacao')


@login_required
def membro_delegacao_delete(request, pk):
    """
    Remove um membro autorizado da delegação.
    """
    membro = get_object_or_404(MembroDelegacao, pk=pk)
    if membro.delegado_principal != request.user:
        messages.error(request, "Acesso negado: Você não tem permissão para remover este membro.")
        return redirect('dashboard')
        
    email = membro.email
    membro.delete()
    messages.success(request, f"E-mail {email} removido da sua delegação.")
    return redirect('membros_delegacao')


# --- SISTEMA DE RECURSOS E NOTIFICAÇÕES ---

class RecursoListView(LoginRequiredMixin, ListView):
    model = Recurso
    template_name = 'core/recurso_list.html'
    context_object_name = 'recursos_andamento'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        if user.is_comissao:
            context['recursos_andamento'] = Recurso.objects.filter(status__in=['aberto', 'parecer_emitido']).order_by('-data_criacao')
            context['recursos_encerrados'] = Recurso.objects.filter(status='encerrado').order_by('-data_criacao')
        else:
            delegacao = user.delegacao_ativa
            context['recursos_andamento'] = Recurso.objects.filter(requerente=delegacao, status__in=['aberto', 'parecer_emitido']).order_by('-data_criacao')
            context['recursos_encerrados'] = Recurso.objects.filter(requerente=delegacao, status='encerrado').order_by('-data_criacao')
            
            # Jogos do time finalizados a menos de 1 hora e sem recurso
            from django.utils import timezone
            import datetime
            one_hour_ago = timezone.now() - datetime.timedelta(hours=1)
            
            jogos_possiveis = Jogo.objects.filter(
                Q(time_a=delegacao) | Q(time_b=delegacao),
                finalizado=True,
                data_hora_fim__gte=one_hour_ago
            ).exclude(recursos__requerente=delegacao).distinct().order_by('-data_hora_fim')
            
            context['jogos_possiveis'] = jogos_possiveis
            
        return context


class RecursoCreateView(LoginRequiredMixin, View):
    def get(self, request, jogo_id):
        delegacao = request.user.delegacao_ativa
        if request.user.is_comissao:
            messages.error(request, "A comissão não pode abrir recursos.")
            return redirect('recurso_list')

        jogo = get_object_or_404(Jogo, pk=jogo_id)

        # Valida se o jogo é do time e se está no prazo de 1h
        if jogo.time_a != delegacao and jogo.time_b != delegacao:
            messages.error(request, "Você não tem permissão para interpor recurso para esta partida.")
            return redirect('recurso_list')

        if not jogo.can_file_recurso:
            messages.error(request, "Prazo expirado: Recursos só podem ser interpostos em até 1h após a finalização da partida.")
            return redirect('recurso_list')

        if Recurso.objects.filter(jogo=jogo, requerente=delegacao).exists():
            messages.error(request, "Você já abriu um recurso para esta partida.")
            return redirect('recurso_list')

        return render(request, 'core/recurso_form.html', {'jogo': jogo})

    def post(self, request, jogo_id):
        delegacao = request.user.delegacao_ativa
        if request.user.is_comissao:
            messages.error(request, "A comissão não pode abrir recursos.")
            return redirect('recurso_list')

        jogo = get_object_or_404(Jogo, pk=jogo_id)

        if jogo.time_a != delegacao and jogo.time_b != delegacao:
            messages.error(request, "Acesso negado.")
            return redirect('recurso_list')

        if not jogo.can_file_recurso:
            messages.error(request, "Prazo expirado para interposição de recurso.")
            return redirect('recurso_list')

        if Recurso.objects.filter(jogo=jogo, requerente=delegacao).exists():
            messages.error(request, "Recurso já interposto.")
            return redirect('recurso_list')

        titulo = request.POST.get('titulo', '').strip()
        corpo = request.POST.get('corpo', '').strip()
        link_anexo = request.POST.get('link_anexo', '').strip()

        if not titulo or not corpo:
            messages.error(request, "Título e corpo são obrigatórios.")
            return render(request, 'core/recurso_form.html', {'jogo': jogo, 'titulo': titulo, 'corpo': corpo, 'link_anexo': link_anexo})

        recurso = Recurso.objects.create(
            jogo=jogo,
            requerente=delegacao,
            titulo=titulo,
            corpo=corpo,
            link_anexo=link_anexo if link_anexo else None
        )

        # Notifica Comissão
        from django.contrib.auth import get_user_model
        User = get_user_model()
        comissao = User.objects.filter(role='COMISSAO')
        for admin in comissao:
            Notificacao.objects.create(
                usuario=admin,
                mensagem=f"Novo recurso interposto pela delegação {delegacao.nome_delegacao or delegacao.email} para a partida {jogo.modalidade.nome}.",
                link=f"/recurso/{recurso.id}/"
            )

        messages.success(request, "Recurso enviado com sucesso!")
        return redirect('recurso_detail', pk=recurso.id)


class RecursoDetailView(LoginRequiredMixin, DetailView):
    model = Recurso
    template_name = 'core/recurso_detail.html'
    context_object_name = 'recurso'

    def get_queryset(self):
        user = self.request.user
        if user.is_comissao:
            return Recurso.objects.all()
        return Recurso.objects.filter(requerente=user.delegacao_ativa)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Verifica se o banner de sucesso deve ser exibido
        recurso = self.get_object()
        has_comissao_replies = recurso.mensagens.filter(remetente__role='COMISSAO').exists()
        context['exibir_banner_sucesso'] = (
            not self.request.user.is_comissao and 
            recurso.status == 'aberto' and 
            not has_comissao_replies
        )
        return context


@login_required
def enviar_mensagem_recurso(request, pk):
    if request.method == 'POST':
        recurso = get_object_or_404(Recurso, pk=pk)
        user = request.user
        
        # Validação de permissão
        if not user.is_comissao and recurso.requerente != user.delegacao_ativa:
            messages.error(request, "Você não tem permissão para interagir com este recurso.")
            return redirect('recurso_list')

        if recurso.status == 'encerrado' and not user.is_comissao:
            messages.error(request, "Este recurso está encerrado e não aceita novos comentários.")
            return redirect('recurso_detail', pk=recurso.id)

        texto = request.POST.get('texto', '').strip()
        if not texto:
            messages.error(request, "A mensagem não pode estar vazia.")
            return redirect('recurso_detail', pk=recurso.id)

        # Salva a mensagem
        RecursoComent = RecursoMensagem.objects.create(
            recurso=recurso,
            remetente=user,
            texto=texto
        )

        # Se for Comissão, atualiza o status ou encerra
        if user.is_comissao:
            novo_status = request.POST.get('novo_status', 'parecer_emitido')
            if novo_status == 'encerrado':
                recurso.status = 'encerrado'
                msg_notif = f"Seu recurso sobre a partida de {recurso.jogo.modalidade.nome} foi respondido e encerrado pela comissão."
            else:
                recurso.status = 'parecer_emitido'
                msg_notif = f"Novo parecer emitido pela comissão no seu recurso da partida de {recurso.jogo.modalidade.nome}."
            
            recurso.save()

            # Notifica o requerente
            Notificacao.objects.create(
                usuario=recurso.requerente,
                mensagem=msg_notif,
                link=f"/recurso/{recurso.id}/"
            )
        else:
            # Reabre recurso se estivesse com parecer
            if recurso.status == 'parecer_emitido':
                recurso.status = 'aberto'
                recurso.save()

            # Notifica comissão
            from django.contrib.auth import get_user_model
            User = get_user_model()
            comissao = User.objects.filter(role='COMISSAO')
            for admin in comissao:
                Notificacao.objects.create(
                    usuario=admin,
                    mensagem=f"Novo comentário da delegação {recurso.requerente.nome_delegacao or recurso.requerente.email} no recurso #{recurso.id}.",
                    link=f"/recurso/{recurso.id}/"
                )

        messages.success(request, "Comentário enviado com sucesso!")
        return redirect('recurso_detail', pk=recurso.id)

    return redirect('recurso_list')


class NotificacaoListView(LoginRequiredMixin, ListView):
    model = Notificacao
    template_name = 'core/notificacao_list.html'
    context_object_name = 'notificacoes'

    def get_queryset(self):
        return Notificacao.objects.filter(usuario=self.request.user).order_by('-data_criacao')


@login_required
def notificacao_ler(request, pk):
    notif = get_object_or_404(Notificacao, pk=pk, usuario=request.user)
    notif.lida = True
    notif.save()
    if notif.link:
        return redirect(notif.link)
    return redirect('dashboard')


@login_required
def notificacoes_limpar(request):
    Notificacao.objects.filter(usuario=request.user, lida=False).update(lida=True)
    messages.success(request, "Todas as notificações foram marcadas como lidas.")
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))


@login_required
@user_passes_test(lambda u: u.is_staff)
def resumo_inscricoes(request):
    from core.models import Campus, Atleta, Modalidade, Inscricao, InscricaoModalidade
    from django.db.models import Count, Q
    import json

    user = request.user
    unread_notifications = Notificacao.objects.filter(usuario=user, lida=False)

    # 1. Totais Gerais
    total_delegacoes = User.objects.filter(role='REPRESENTANTE', parent_delegate__isnull=True, inscricao__isnull=False).count()
    total_inscricoes = Inscricao.objects.count()
    total_atletas = Atleta.objects.count()
    total_modalidades = Modalidade.objects.count()

    # Atletas por Gênero
    atletas_m = Atleta.objects.filter(genero='M').count()
    atletas_f = Atleta.objects.filter(genero='F').count()
    atletas_n = Atleta.objects.filter(genero='N').count()

    # Atletas por Tipo
    atletas_estudantes = Atleta.objects.filter(tipo_atleta='estudante').count()
    atletas_servidores = Atleta.objects.filter(tipo_atleta='servidor').count()

    # 2. Resumo por Campus
    campi = list(Campus.objects.all().exclude(nome__icontains='Teófilo Otoni').order_by('nome'))
    for c in campi:
        c.nome_curto = c.nome.replace("Campus de ", "").replace("Campus ", "")
    campus_summary = []
    
    chart_campus_labels = []
    chart_delegacoes_data = []
    chart_atletas_data = []
    
    for c in campi:
        delegacoes_c = User.objects.filter(
            role='REPRESENTANTE',
            parent_delegate__isnull=True,
            inscricao__isnull=False,
            atletas__campus=c
        ).distinct().count()
        
        atletas_c = Atleta.objects.filter(campus=c).count()
        
        modalidades_c = InscricaoModalidade.objects.filter(
            inscricao__delegacao__atletas__campus=c
        ).values('modalidade').distinct().count()
        
        campus_summary.append({
            'nome': c.nome,
            'delegacoes': delegacoes_c,
            'atletas': atletas_c,
            'modalidades': modalidades_c,
        })
        
        chart_campus_labels.append(c.nome)
        chart_delegacoes_data.append(delegacoes_c)
        chart_atletas_data.append(atletas_c)

    # Encontrar o campus com maior participação
    campus_maior_participacao = "Nenhum"
    if campus_summary:
        maior_campus = max(campus_summary, key=lambda x: x['atletas'])
        if maior_campus['atletas'] > 0:
            campus_maior_participacao = maior_campus['nome'].replace("Campus ", "")

    if atletas_estudantes > atletas_servidores:
        categoria_predominante = "Estudantes"
    elif atletas_servidores > atletas_estudantes:
        categoria_predominante = "Servidores"
    else:
        categoria_predominante = "Equilibrada" if total_atletas > 0 else "Nenhuma"

    pct_estudantes = round((atletas_estudantes / total_atletas) * 100) if total_atletas > 0 else 0
    pct_servidores = round((atletas_servidores / total_atletas) * 100) if total_atletas > 0 else 0
    
    pct_masculino = round((atletas_m / total_atletas) * 100) if total_atletas > 0 else 0
    pct_feminino = round((atletas_f / total_atletas) * 100) if total_atletas > 0 else 0
    pct_nb = round((atletas_n / total_atletas) * 100) if total_atletas > 0 else 0

    # 3. Resumo por Modalidade
    modalidades = Modalidade.objects.all().order_by('nome')
    modalidade_summary = []
    for m in modalidades:
        times_count = m.inscricoes.count()
        atletas_count = Atleta.objects.filter(modalidades_inscritas__modalidade=m).distinct().count()
        
        campi_inscritos = Campus.objects.filter(
            atleta__modalidades_inscritas__modalidade=m
        ).distinct()
        
        campi_counts = []
        for c in campi:
            count = InscricaoModalidade.objects.filter(
                modalidade=m,
                inscricao__delegacao__atletas__campus=c
            ).distinct().count()
            campi_counts.append(count)
        
        modalidade_summary.append({
            'nome': m.nome,
            'genero': m.get_genero_display(),
            'inscricoes': times_count,
            'atletas': atletas_count,
            'campi': ", ".join([c.nome for c in campi_inscritos]) if campi_inscritos.exists() else "Nenhum",
            'campi_counts': campi_counts,
        })

    # 4. Dados para o gráfico de Modalidades por Campus (Y-axis: Modalidades, Datasets: Campi)
    chart_modalidade_labels = []
    campus_datasets_data = {c.id: [] for c in campi}

    for m in modalidades:
        # Só inclui modalidades com pelo menos uma inscrição para otimizar espaço
        if m.inscricoes.exists():
            chart_modalidade_labels.append(f"{m.nome} ({m.get_genero_display()})")
            for c in campi:
                count = InscricaoModalidade.objects.filter(
                    modalidade=m,
                    inscricao__delegacao__atletas__campus=c
                ).distinct().count()
                campus_datasets_data[c.id].append(count)

    chart_datasets_modalidades = []
    colors = [
        'rgba(59, 130, 246, 0.8)',   # Azul
        'rgba(139, 92, 246, 0.8)',   # Roxo
        'rgba(249, 115, 22, 0.8)',   # Laranja
        'rgba(16, 185, 129, 0.8)',   # Verde
    ]
    border_colors = [c.replace('0.8', '1') for c in colors]

    for index, c in enumerate(campi):
        color_index = index % len(colors)
        chart_datasets_modalidades.append({
            'label': c.nome,
            'data': campus_datasets_data[c.id],
            'backgroundColor': colors[color_index],
            'borderColor': border_colors[color_index],
            'borderWidth': 1.5,
            'borderRadius': 4,
        })

    # 5. Resumo de Modalidades por Delegação
    inscricoes_list = Inscricao.objects.select_related('delegacao').prefetch_related(
        'modalidades__modalidade',
        'modalidades__atletas__campus'
    ).order_by('delegacao__nome_delegacao', 'delegacao__email')

    context = {
        'unread_notifications': unread_notifications,
        'total_delegacoes': total_delegacoes,
        'total_inscricoes': total_inscricoes,
        'total_atletas': total_atletas,
        'total_modalidades': total_modalidades,
        
        'atletas_m': atletas_m,
        'atletas_f': atletas_f,
        'atletas_n': atletas_n,
        'pct_masculino': pct_masculino,
        'pct_feminino': pct_feminino,
        'pct_nb': pct_nb,
        
        'atletas_estudantes': atletas_estudantes,
        'atletas_servidores': atletas_servidores,
        'pct_estudantes': pct_estudantes,
        'pct_servidores': pct_servidores,
        'categoria_predominante': categoria_predominante,
        'campus_maior_participacao': campus_maior_participacao,
        
        'campi': campi,
        'campus_summary': campus_summary,
        'modalidade_summary': modalidade_summary,
        'inscricoes_list': inscricoes_list,
        
        'chart_campus_labels_json': json.dumps(chart_campus_labels),
        'chart_modalidade_labels_json': json.dumps(chart_modalidade_labels),
        'chart_delegacoes_data_json': json.dumps(chart_delegacoes_data),
        'chart_atletas_data_json': json.dumps(chart_atletas_data),
        'chart_datasets_modalidades_json': json.dumps(chart_datasets_modalidades),
    }
    return render(request, 'core/resumo_inscricoes.html', context)


