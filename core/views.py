from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.db import models
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import login, logout
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from .models import Atleta, Modalidade, Jogo, PreSumula, PreSumulaAtleta, Inscricao, InscricaoModalidade, Recurso, RecursoMensagem, Notificacao, ConfiguracaoPeriodoInscricao, SubstituicaoAtleta
from .forms import RegisterForm, AtletaForm, JogoForm, ModalidadeForm, ConfiguracaoPeriodoInscricaoForm
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
            context['total_inscricoes'] = Inscricao.objects.count()
            
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
        ).filter(time_a__in=User.objects.all(), time_b__in=User.objects.all()).order_by('-data_jogo', '-horario_jogo', '-id')
        
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
        ).filter(time_a__in=User.objects.all(), time_b__in=User.objects.all()).order_by('-data_jogo', '-horario_jogo', '-id')
        
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
        
        from .models import ConfiguracaoPeriodoInscricao
        has_config = ConfiguracaoPeriodoInscricao.objects.exists()
        context['olimpiadas_ativas'] = has_config
        if has_config:
            context['modalidades_abertas'] = Modalidade.objects.filter(inscricoes_abertas=True)
        else:
            context['modalidades_abertas'] = Modalidade.objects.none()
        
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
        jogo = form.save(commit=False)
        if not form.cleaned_data.get('finalizado'):
            jogo.finalizado = False
            jogo.data_hora_fim = None
        jogo.save()
        form.save_m2m()
        if not jogo.is_presumula_deadline_passed and not jogo.finalizado:
            deadline_str = f" até às {jogo.presumula_deadline.strftime('%H:%M')}" if jogo.presumula_deadline else ""
            messages.success(self.request, f"Dados do jogo atualizados com sucesso! A pré-súmula está aberta{deadline_str}.")
        else:
            messages.success(self.request, "Dados do jogo atualizados com sucesso!")
        return redirect(self.success_url)


@login_required
def jogo_ajustar_horario(request, pk):
    """
    Permite à Comissão Organizadora intervir e alterar o horário/data da partida diretamente
    a partir da seção de pré-súmulas, possibilitando que em casos de atrasos na quadra/programação
    a pré-súmula possa ser reaberta para preenchimento pelas equipes.
    """
    if not (request.user.is_staff or request.user.is_comissao):
        messages.error(request, "Acesso negado: Apenas a comissão organizadora pode intervir e alterar o horário da partida.")
        return redirect('presumula_list')

    if request.method == 'POST':
        jogo = get_object_or_404(Jogo, pk=pk)
        data_str = request.POST.get('data_jogo')
        horario_str = request.POST.get('horario_jogo')

        if not data_str or not horario_str:
            messages.error(request, "Data e horário do jogo são obrigatórios para alterar a programação.")
            return redirect('presumula_list')

        import datetime
        from django.core.exceptions import ValidationError

        try:
            nova_data = datetime.datetime.strptime(data_str, '%Y-%m-%d').date()
            novo_horario = datetime.datetime.strptime(horario_str, '%H:%M').time()
        except ValueError:
            messages.error(request, "Formato de data ou horário inválido.")
            return redirect('presumula_list')

        jogo.data_jogo = nova_data
        jogo.horario_jogo = novo_horario
        # Ao reprogramar a partida para intervir em atraso, reabre o jogo
        jogo.finalizado = False
        jogo.data_hora_fim = None

        if 'permitir_lancamento_atletas' in request.POST:
            jogo.permitir_lancamento_atletas = True
        elif request.POST.get('has_permitir_atletas_field') == '1':
            jogo.permitir_lancamento_atletas = False

        try:
            jogo.full_clean()
            jogo.save()

            # Sincroniza partida de chaveamento se houver
            partida = jogo.partida_chaveamento.first()
            if partida:
                partida.permitir_lancamento_atletas = jogo.permitir_lancamento_atletas
                partida.save()

            horario_formatado = novo_horario.strftime('%H:%M')
            data_formatada = nova_data.strftime('%d/%m/%Y')

            if jogo.permitir_lancamento_atletas:
                messages.success(
                    request,
                    f"Horário da partida {jogo.modalidade.nome} atualizado para {data_formatada} às {horario_formatado} e lançamento de atletas LIBERADO fora do prazo para esta partida!"
                )
            elif not jogo.is_presumula_deadline_passed:
                deadline_formatado = jogo.presumula_deadline.strftime('%H:%M') if jogo.presumula_deadline else ''
                messages.success(
                    request,
                    f"Horário da partida {jogo.modalidade.nome} atualizado para {data_formatada} às {horario_formatado}! A pré-súmula foi REABERTA com sucesso (prazo de escalação até às {deadline_formatado})."
                )
            else:
                messages.warning(
                    request,
                    f"Horário da partida atualizado para {data_formatada} às {horario_formatado}. Como o novo horário está com menos de 1 hora de antecedência em relação a agora, o prazo do regulamento manteve a pré-súmula encerrada. Você pode ativar o botão 'Permitir lançar atletas' para liberá-la sem precisar mudar o horário."
                )
        except ValidationError as e:
            err_msg = "; ".join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]) if hasattr(e, 'message_dict') else str(e)
            messages.error(request, f"Não foi possível atualizar o horário: {err_msg}")

        return redirect('presumula_list')


@login_required
def jogo_toggle_permitir_atletas(request, pk):
    """
    Permite à Comissão Organizadora alternar a permissão de lançamento/escalação
    de atletas fora do prazo para um jogo específico com um clique.
    """
    if not (request.user.is_staff or getattr(request.user, 'is_comissao', False) or request.user.is_superuser):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({'error': 'Acesso negado: apenas a comissão organizadora pode alterar esta permissão.'}, status=403)
        messages.error(request, "Acesso negado.")
        return redirect('presumula_list')

    if request.method == 'POST':
        jogo = get_object_or_404(Jogo, pk=pk)

        # Inverte o estado atual
        novo_estado = not jogo.permitir_lancamento_atletas
        jogo.permitir_lancamento_atletas = novo_estado

        if novo_estado:
            # Ao liberar lançamento, se o jogo estava finalizado sem placares reais (por prazo), reabre
            if jogo.finalizado and not jogo.wo_tipo and jogo.placar_time_a is None and jogo.placar_time_b is None:
                jogo.finalizado = False
                jogo.data_hora_fim = None
            msg = f"Lançamento de atletas LIBERADO para o jogo {jogo.modalidade.nome} ({jogo.time_a_display} vs {jogo.time_b_display})! As delegações agora podem escalar atletas mesmo após o prazo regulamentar."
        else:
            msg = f"Lançamento de atletas BLOQUEADO para o jogo {jogo.modalidade.nome}. O sistema voltou a aplicar o prazo regulamentar normalmente."

        jogo.save()

        # Sincroniza partida de chaveamento vinculada se existir
        partida = jogo.partida_chaveamento.first()
        if partida:
            partida.permitir_lancamento_atletas = novo_estado
            if novo_estado and partida.finalizada and not partida.wo_tipo and partida.placar_a is None and partida.placar_b is None:
                partida.finalizada = False
            partida.save()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({
                'success': True,
                'permitir_lancamento_atletas': novo_estado,
                'message': msg
            })

        messages.success(request, msg)
        return redirect(request.META.get('HTTP_REFERER', 'presumula_list'))

    return redirect('presumula_list')

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
        
        from django.core.exceptions import ObjectDoesNotExist
        try:
            nome_a = jogo.time_a.nome_delegacao or jogo.time_a.email
        except ObjectDoesNotExist:
            nome_a = "Time Inexistente"
        try:
            nome_b = jogo.time_b.nome_delegacao or jogo.time_b.email
        except ObjectDoesNotExist:
            nome_b = "Time Inexistente"
            
        messages.success(request, f"O jogo {jogo.modalidade.nome} ({nome_a} vs {nome_b}) foi encerrado com sucesso!")
    return redirect('presumula_list')



# Remoção de avaliar_equipe de inscrições legadas

@login_required
def enviar_correcao_atleta(request, pk):
    atleta = get_object_or_404(Atleta, pk=pk)
    delegacao_user = request.user.delegacao_ativa
    delegacao_atleta = atleta.cadastrado_por.delegacao_ativa if hasattr(atleta.cadastrado_por, 'delegacao_ativa') else atleta.cadastrado_por
    if not (request.user.is_comissao or request.user.is_staff or delegacao_user == delegacao_atleta or atleta.cadastrado_por == request.user):
        messages.error(request, "Você não tem permissão para alterar este atleta.")
        return redirect(request.META.get('HTTP_REFERER', 'dashboard'))

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

# Helper functions for inscription periods and athlete association
def get_periodo_inscricao_ativo():
    """
    Retorna uma tupla (ativo: bool, tipo: str | None) indicando se há um período
    de inscrições aberto no momento:
    - (True, 'regular') para período regular de 1ª chamada
    - (True, 'segunda_chamada') para período de 2ª chamada
    - (False, None) se não houver período ativo
    """
    from django.utils import timezone
    from .models import ConfiguracaoPeriodoInscricao
    
    config = ConfiguracaoPeriodoInscricao.objects.first()
    if not config:
        return False, None
        
    now = timezone.now()
    if config.data_inicio and config.data_fim and (config.data_inicio <= now <= config.data_fim):
        return True, 'regular'
        
    if config.segunda_chamada_inicio and config.segunda_chamada_fim and (config.segunda_chamada_inicio <= now <= config.segunda_chamada_fim):
        return True, 'segunda_chamada'
        
    return False, None


def associar_atletas_a_inscricao_se_aberta(delegacao, novos_atletas):
    """
    Se houver período de inscrição ativo (1ª chamada regular ou 2ª chamada) e a delegação
    já possuir uma Inscrição oficial enviada, vincula automaticamente os novos atletas criados
    às modalidades da inscrição, reseta o status da inscrição e delegação para 'pendente'
    e notifica a comissão organizadora.
    """
    ativo, tipo_periodo = get_periodo_inscricao_ativo()
    if not ativo or not delegacao:
        return False
        
    inscricao = getattr(delegacao, 'inscricao', None)
    if not inscricao:
        return False
        
    modalidades = inscricao.modalidades.all()
    if not modalidades.exists():
        return False
        
    if isinstance(novos_atletas, (list, tuple, set, models.QuerySet)):
        atletas_list = list(novos_atletas)
    else:
        atletas_list = [novos_atletas]
        
    if not atletas_list:
        return False
        
    # Vincula os atletas às modalidades
    for im in modalidades:
        im.atletas.add(*atletas_list)
        
    # Reseta status dos atletas para que apareçam como pendentes na avaliação
    for at in atletas_list:
        at.status_avaliacao = 'nao_avaliado'
        at.em_conformidade = False
        at.save(update_fields=['status_avaliacao', 'em_conformidade'])
        
    # Reseta status da inscrição e da delegação para reavaliação da comissão
    inscricao.status = 'pendente'
    inscricao.save(update_fields=['status'])
    
    delegacao.status_delegacao = 'pendente'
    delegacao.justificativa_delegacao = ''
    delegacao.save(update_fields=['status_delegacao', 'justificativa_delegacao'])
    
    # Notifica a comissão organizadora
    motivo = "na Segunda Chamada" if tipo_periodo == 'segunda_chamada' else "no período de inscrições"
    comissao = User.objects.filter(role='COMISSAO')
    for admin in comissao:
        Notificacao.objects.create(
            usuario=admin,
            mensagem=f"Novos atletas adicionados {motivo} pela delegação {delegacao.nome_delegacao or delegacao.email}.",
            link='/comissao/delegacoes/'
        )
        
    return True


# Atletas Views
class AtletaListView(LoginRequiredMixin, ListView):
    model = Atleta
    template_name = 'core/atleta_list.html'
    context_object_name = 'atletas'

    def get_queryset(self):
        return Atleta.objects.filter(
            cadastrado_por=self.request.user.delegacao_ativa
        ).prefetch_related('modalidades_inscritas__modalidade').order_by('-id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        delegacao = self.request.user.delegacao_ativa
        inscricao = getattr(delegacao, 'inscricao', None)
        context['inscricao'] = inscricao
        if inscricao:
            substituidos_ids = set(inscricao.substituicoes.values_list('atleta_saiu_id', flat=True))
            atletas_ids_inscritos = set(
                Atleta.objects.filter(modalidades_inscritas__inscricao=inscricao).exclude(id__in=substituidos_ids).values_list('id', flat=True)
            )
            context['atletas_ids_inscritos'] = atletas_ids_inscritos
            context['total_nao_inscritos'] = Atleta.objects.filter(
                cadastrado_por=delegacao
            ).exclude(id__in=atletas_ids_inscritos).exclude(id__in=substituidos_ids).count()
        else:
            context['atletas_ids_inscritos'] = set()
            context['total_nao_inscritos'] = 0
        return context

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
        novos_atletas = []
        delegacao = request.user.delegacao_ativa
        for i in range(len(nomes)):
            if nomes[i].strip():
                is_egr = (is_egressos[i] == '1') if i < len(is_egressos) else False
                gen = generos[i] if i < len(generos) else 'M'
                tipo_atl = tipo_atletas[i] if i < len(tipo_atletas) else 'estudante'
                link_doc = links_documentos[i] if i < len(links_documentos) else ''
                
                # Fetch selected campus ID
                c_id = int(campi[i]) if i < len(campi) and campi[i].isdigit() else None
                
                atleta = Atleta.objects.create(
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
                    cadastrado_por=delegacao
                )
                novos_atletas.append(atleta)
                atletas_criados += 1
        
        if novos_atletas:
            vinculado = associar_atletas_a_inscricao_se_aberta(delegacao, novos_atletas)
            if vinculado:
                messages.success(request, f"{atletas_criados} atleta(s) cadastrado(s) e vinculado(s) à inscrição oficial com sucesso! A Comissão Organizadora fará a avaliação.")
            else:
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
        # Se houver período de inscrição ativo (1ª ou 2ª chamada), sincroniza atletas da delegação com a inscrição
        ativo, tipo_periodo = get_periodo_inscricao_ativo()
        if ativo:
            for insc in Inscricao.objects.prefetch_related('modalidades', 'substituicoes').all():
                # Remove atletas substituídos de im.atletas se ainda estiverem vinculados
                subs_saiu_ids = list(insc.substituicoes.values_list('atleta_saiu_id', flat=True))
                if subs_saiu_ids:
                    for im in insc.modalidades.all():
                        im.atletas.remove(*subs_saiu_ids)

                unlinked = insc.atletas_nao_inscritos
                if unlinked.exists():
                    for im in insc.modalidades.all():
                        im.atletas.add(*unlinked)

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
        
        # Garante vínculo com a inscrição da delegação se existir
        delegacao = atleta.cadastrado_por
        inscricao = getattr(delegacao, 'inscricao', None)
        if inscricao and not atleta.modalidades_inscritas.filter(inscricao=inscricao).exists():
            for im in inscricao.modalidades.all():
                im.atletas.add(atleta)
                
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
            qs = Jogo.objects.filter(time_a__in=User.objects.all(), time_b__in=User.objects.all())
        else:
            delegacao = user.delegacao_ativa
            if delegacao.role == 'REPRESENTANTE' and delegacao.status_delegacao != 'deferido':
                return Jogo.objects.none()
            qs = Jogo.objects.filter(
                Q(time_a=delegacao) | Q(time_b=delegacao)
            ).filter(time_a__in=User.objects.all(), time_b__in=User.objects.all())
            
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
        context['delegacoes_list'] = User.objects.filter(role='REPRESENTANTE', status_delegacao='deferido', parent_delegate__isnull=True).order_by('nome_delegacao')
        
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
        if not request.user.is_staff and jogo.time_a_id != delegacao.id and jogo.time_b_id != delegacao.id:
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
            
        # Filtra os atletas da delegação em conformidade e pelo sexo da categoria (excluindo substituídos)
        genero_modalidade = jogo.modalidade.genero
        substituidos_ids = list(SubstituicaoAtleta.objects.filter(inscricao__delegacao=delegacao).values_list('atleta_saiu_id', flat=True))
        atletas = Atleta.objects.filter(cadastrado_por=delegacao, em_conformidade=True).exclude(id__in=substituidos_ids)
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
        
        if not request.user.is_staff and jogo.time_a_id != delegacao.id and jogo.time_b_id != delegacao.id:
            messages.error(request, "Acesso negado.")
            return redirect('presumula_list')

        # Verifica limite de 1h antes do jogo
        if not request.user.is_staff and jogo.is_presumula_deadline_passed:
            messages.error(request, "Prazo encerrado: A pré-súmula deve ser preenchida em até 1h antes do jogo. WO foi aplicado.")
            return redirect('presumula_list')
            
        if PreSumula.objects.filter(jogo=jogo, representante=delegacao).exists():
            messages.error(request, "Você já preencheu a pré-súmula para este jogo.")
            return redirect('presumula_list')
            
        substituidos_ids = set(SubstituicaoAtleta.objects.filter(inscricao__delegacao=delegacao).values_list('atleta_saiu_id', flat=True))
        atleta_ids = [aid for aid in request.POST.getlist('atletas') if int(aid) not in substituidos_ids]
        tecnico = request.POST.get('tecnico', '').strip()

        # Validar número de atletas contra limites da modalidade
        min_atletas = jogo.modalidade.limite_minimo_jogadores
        max_atletas = jogo.modalidade.limite_maximo_jogadores
        num_selecionados = len(atleta_ids)

        if num_selecionados < min_atletas or num_selecionados > max_atletas:
            limit_msg = f"no mínimo {min_atletas}" if num_selecionados < min_atletas else f"no máximo {max_atletas}"
            messages.error(request, f"Erro: A escalação deve conter {limit_msg} atleta(s) para a modalidade {jogo.modalidade.nome}. (Selecionados: {num_selecionados})")
            
            genero_modalidade = jogo.modalidade.genero
            atletas = Atleta.objects.filter(cadastrado_por=delegacao, em_conformidade=True).exclude(id__in=substituidos_ids)
            if genero_modalidade == 'M':
                atletas = atletas.filter(genero__in=['M', 'N'])
            elif genero_modalidade == 'F':
                atletas = atletas.filter(genero__in=['F', 'N'])
                
            for a in atletas:
                a.is_escalado = str(a.id) in atleta_ids
                a.camisa = request.POST.get(f'camisa_{a.id}', '')

            atletas = sorted(
                atletas,
                key=lambda a: (0 if a.is_escalado else 1, int(a.camisa) if (a.is_escalado and str(a.camisa).isdigit()) else 999999, a.nome_completo)
            )
                
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
            if numero_camisa is not None and str(numero_camisa).strip() != '':
                try:
                    num_camisa = int(numero_camisa)
                except (ValueError, TypeError):
                    num_camisa = 0
                PreSumulaAtleta.objects.create(
                    presumula=presumula,
                    atleta_id=atleta_id,
                    numero_camisa=num_camisa
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
        
        # Filtra os atletas da delegação em conformidade e pelo sexo da categoria (excluindo substituídos)
        substituidos_ids = list(SubstituicaoAtleta.objects.filter(inscricao__delegacao=presumula.representante).values_list('atleta_saiu_id', flat=True))
        atletas = Atleta.objects.filter(cadastrado_por=presumula.representante, em_conformidade=True).exclude(id__in=substituidos_ids)
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

        # Ordena dinamicamente: escalados primeiro (por número de camisa crescente), seguidos pelos não escalados
        atletas = sorted(
            atletas,
            key=lambda a: (0 if a.is_escalado else 1, int(a.camisa) if (a.is_escalado and str(a.camisa).isdigit()) else 999999, a.nome_completo)
        )

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

        substituidos_ids = set(SubstituicaoAtleta.objects.filter(inscricao__delegacao=delegacao).values_list('atleta_saiu_id', flat=True))
        atleta_ids = [aid for aid in request.POST.getlist('atletas') if int(aid) not in substituidos_ids]
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
            atletas = Atleta.objects.filter(cadastrado_por=presumula.representante, em_conformidade=True).exclude(id__in=substituidos_ids)
            if genero_modalidade == 'M':
                atletas = atletas.filter(genero__in=['M', 'N'])
            elif genero_modalidade == 'F':
                atletas = atletas.filter(genero__in=['F', 'N'])
                
            for a in atletas:
                a.is_escalado = str(a.id) in atleta_ids
                a.camisa = request.POST.get(f'camisa_{a.id}', '')

            # Ordena dinamicamente: escalados primeiro (por número de camisa crescente), seguidos pelos não escalados
            atletas = sorted(
                atletas,
                key=lambda a: (0 if a.is_escalado else 1, int(a.camisa) if (a.is_escalado and str(a.camisa).isdigit()) else 999999, a.nome_completo)
            )

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
            if numero_camisa is not None and str(numero_camisa).strip() != '':
                try:
                    num_camisa = int(numero_camisa)
                except (ValueError, TypeError):
                    num_camisa = 0
                PreSumulaAtleta.objects.create(
                    presumula=presumula,
                    atleta_id=atleta_id,
                    numero_camisa=num_camisa
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
        if self.request.user.is_staff or self.request.user.is_comissao:
            return PreSumula.objects.all()
        return PreSumula.objects.filter(representante=self.request.user.delegacao_ativa)


class PreSumulaDeleteAllView(LoginRequiredMixin, View):
    """
    Exclui TODOS os jogos e pré-súmulas cadastrados no sistema.
    Disponível apenas para a Comissão Organizadora (staff / comissão).
    """
    def post(self, request):
        if not (request.user.is_staff or request.user.is_comissao):
            messages.error(request, "Acesso negado: Apenas a comissão organizadora pode realizar esta ação.")
            return redirect('presumula_list')
        
        jogos_count, _ = Jogo.objects.all().delete()
        presumulas_count, _ = PreSumula.objects.all().delete()
        
        messages.success(request, f"Limpeza concluída: {jogos_count} jogo(s) e {presumulas_count} pré-súmula(s) foram apagados com sucesso.")
        return redirect('presumula_list')


class PreSumulaDeleteView(LoginRequiredMixin, View):
    """
    Exclui uma pré-súmula específica.
    Disponível apenas para a Comissão Organizadora.
    """
    def post(self, request, pk):
        presumula = get_object_or_404(PreSumula, pk=pk)
        user = request.user
        
        if not (user.is_staff or user.is_comissao):
            messages.error(request, "Você não tem permissão para remover pré-súmulas. Apenas a comissão organizadora pode excluir.")
            return redirect('presumula_list')
            
        presumula.delete()
        messages.success(request, "Pré-súmula removida com sucesso.")
        return redirect('presumula_list')


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
    from .models import ConfiguracaoPeriodoInscricao
    
    config = ConfiguracaoPeriodoInscricao.objects.first()
    now = timezone.now()
    status_inscricao = 'nao_cadastrada'
    data_inicio = None
    data_fim = None
    
    if config:
        data_inicio = config.data_inicio
        data_fim = config.data_fim
        is_segunda_chamada_active = config.segunda_chamada_inicio and config.segunda_chamada_fim and (config.segunda_chamada_inicio <= now <= config.segunda_chamada_fim)
        
        if is_segunda_chamada_active:
            status_inscricao = 'segunda_chamada'
        elif now < config.data_inicio:
            status_inscricao = 'nao_iniciada'
        elif now > config.data_fim:
            status_inscricao = 'encerrada'
        else:
            status_inscricao = 'aberta'
            
    if request.method == 'POST':
        if status_inscricao != 'aberta':
            messages.error(request, "As inscrições estão fora do período permitido.")
            return redirect('inscricao_passo1')
            
        selected_modalidades = request.POST.getlist('modalidades')
        if not selected_modalidades:
            messages.error(request, "Por favor, selecione ao menos uma modalidade para se inscrever.")
            return redirect('inscricao_passo1')
            
        request.session['inscricao_modalidades_ids'] = [int(mid) for mid in selected_modalidades]
        return redirect('inscricao_passo2')
        
    if config:
        modalidades = Modalidade.objects.filter(inscricoes_abertas=True)
    else:
        modalidades = Modalidade.objects.none()
        
    return render(request, 'core/inscricao_passo1.html', {
        'modalidades': modalidades,
        'status_inscricao': status_inscricao,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'config': config
    })


@login_required
def inscricao_passo2(request):
    if request.user.is_comissao:
        return redirect('dashboard')
    delegacao = request.user.delegacao_ativa
    inscricao = getattr(delegacao, 'inscricao', None)
    if inscricao:
        return redirect('inscricao_detail')
        
    from django.utils import timezone
    from .models import ConfiguracaoPeriodoInscricao
    
    config = ConfiguracaoPeriodoInscricao.objects.first()
    now = timezone.now()
    if config and (now < config.data_inicio or now > config.data_fim):
        messages.error(request, "As inscrições estão fora do período permitido.")
        return redirect('inscricao_passo1')
        
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
    
    from django.utils import timezone
    from .models import ConfiguracaoPeriodoInscricao
    
    config = ConfiguracaoPeriodoInscricao.objects.first()
    now = timezone.now()
    is_segunda_chamada_active = config and config.segunda_chamada_inicio and config.segunda_chamada_fim and (config.segunda_chamada_inicio <= now <= config.segunda_chamada_fim)
    
    return render(request, 'core/inscricao_detail.html', {
        'inscricao': inscricao,
        'modalidades_inscritas': modalidades_inscritas,
        'atletas_inscritos': inscricao.atletas_inscritos,
        'is_segunda_chamada_active': is_segunda_chamada_active
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
        if jogo.time_a_id != delegacao.id and jogo.time_b_id != delegacao.id:
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

        if jogo.time_a_id != delegacao.id and jogo.time_b_id != delegacao.id:
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

        if recurso.status == 'encerrado':
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

    def calculate_percentage(count, total):
        if total == 0 or count == 0:
            return 0
        pct = (count / total) * 100
        if pct < 0.5:
            return round(pct, 1)
        if pct > 99.5 and count < total:
            return round(pct, 1)
        return round(pct)

    pct_estudantes = calculate_percentage(atletas_estudantes, total_atletas)
    pct_servidores = calculate_percentage(atletas_servidores, total_atletas)
    
    pct_masculino = calculate_percentage(atletas_m, total_atletas)
    pct_feminino = calculate_percentage(atletas_f, total_atletas)
    pct_nb = calculate_percentage(atletas_n, total_atletas)


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

    # 6. Resumo de Delegações por Modalidade
    modalidades_com_delegacoes = Modalidade.objects.prefetch_related(
        'inscricoes__inscricao__delegacao',
        'inscricoes__atletas',
        'inscricoes__inscricao__delegacao__atletas__campus'
    ).order_by('nome')

    # 7. Dados da Análise Quantitativa
    campi_all = Campus.objects.all().order_by('nome')
    campi_stats = []
    total_servidores_global = Atleta.objects.filter(tipo_atleta='servidor').count()
    total_estudantes_global = Atleta.objects.filter(tipo_atleta='estudante').count()
    total_inscritos_global = Atleta.objects.count()

    for campus in campi_all:
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
        
    max_members = max([s['total_membros'] for s in campi_stats], default=0)

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
        'modalidades_com_delegacoes': modalidades_com_delegacoes,

        'campi_stats': campi_stats,
        'total_servidores_global': total_servidores_global,
        'total_estudantes_global': total_estudantes_global,
        'total_inscritos_global': total_inscritos_global,
        'max_members': max_members,
        
        'chart_campus_labels_json': json.dumps(chart_campus_labels),
        'chart_modalidade_labels_json': json.dumps(chart_modalidade_labels),
        'chart_delegacoes_data_json': json.dumps(chart_delegacoes_data),
        'chart_atletas_data_json': json.dumps(chart_atletas_data),
        'chart_datasets_modalidades_json': json.dumps(chart_datasets_modalidades),
    }
    return render(request, 'core/resumo_inscricoes.html', context)


from django.views import View

class AdminPeriodoInscricaoView(LoginRequiredMixin, View):
    """
    Permite à Comissão Organizadora configurar o período de inscrições das Olimpíadas.
    """
    def get(self, request):
        if not request.user.is_comissao:
            return redirect('dashboard')
        config = ConfiguracaoPeriodoInscricao.objects.first()
        editing = bool(request.GET.get('edit')) or not config
        
        status_inscricao = 'aberta'
        if config:
            from django.utils import timezone
            now = timezone.now()
            if now < config.data_inicio:
                status_inscricao = 'nao_iniciada'
            elif now > config.data_fim:
                is_segunda_chamada_active = config.segunda_chamada_inicio and config.segunda_chamada_fim and (config.segunda_chamada_inicio <= now <= config.segunda_chamada_fim)
                if is_segunda_chamada_active:
                    status_inscricao = 'segunda_chamada'
                else:
                    status_inscricao = 'encerrada'
            else:
                status_inscricao = 'aberta'
        else:
            status_inscricao = 'nao_cadastrada'

        second_only = bool(request.GET.get('second_only'))
        if status_inscricao == 'segunda_chamada':
            second_only = True
            
        form = ConfiguracaoPeriodoInscricaoForm(instance=config) if editing else None
        
        return render(request, 'core/admin_periodo_inscricao.html', {
            'form': form, 
            'object': config,
            'editing': editing,
            'second_only': second_only,
            'status_inscricao': status_inscricao
        })

    def post(self, request):
        if not request.user.is_comissao:
            return redirect('dashboard')
        config = ConfiguracaoPeriodoInscricao.objects.first()
        
        # Handle exclusion of dates (Encerrar Olimpíadas)
        if 'delete_period' in request.POST:
            if config:
                config.delete()
            
            from core.models import Inscricao, PreSumula, Atleta, Recurso, Jogo
            from django.contrib.auth import get_user_model
            
            # 1. Delete all inscriptions (cascade-deletes modalidade choices and substitutions)
            Inscricao.objects.all().delete()
            
            # 2. Delete all pre-súmulas, resources and games
            PreSumula.objects.all().delete()
            Recurso.objects.all().delete()
            Jogo.objects.all().delete()
            
            # 3. Reset representatives/delegations registration statuses and payment fields
            User = get_user_model()
            User.objects.filter(role='REPRESENTANTE').update(
                status_delegacao='pendente',
                justificativa_delegacao=None,
                link_comprovante_pagamento=None,
                status_pagamento='nao_avaliado',
                justificativa_pagamento=None
            )
            
            # 4. Reset athletes' document verification statuses
            Atleta.objects.all().update(
                status_avaliacao='nao_avaliado',
                em_conformidade=False,
                justificativa_inconformidade=None,
                permite_correcao=False,
                link_correcao=None
            )
            
            messages.warning(request, "As Olimpíadas foram encerradas: todas as inscrições, pré-súmulas e comprovantes foram apagados, e o status das delegações e atletas foi resetado para permitir um novo período.")
            return redirect('admin_periodo_inscricao')

        if not config:
            config = ConfiguracaoPeriodoInscricao()
            
        status_inscricao = 'aberta'
        from django.utils import timezone
        now = timezone.now()
        if config.pk:
            if now < config.data_inicio:
                status_inscricao = 'nao_iniciada'
            elif now > config.data_fim:
                is_segunda_chamada_active = config.segunda_chamada_inicio and config.segunda_chamada_fim and (config.segunda_chamada_inicio <= now <= config.segunda_chamada_fim)
                if is_segunda_chamada_active:
                    status_inscricao = 'segunda_chamada'
                else:
                    status_inscricao = 'encerrada'
            else:
                status_inscricao = 'aberta'
        else:
            status_inscricao = 'nao_cadastrada'

        second_only = bool(request.GET.get('second_only')) or (status_inscricao == 'segunda_chamada')
        original_data_inicio = config.data_inicio if config.pk else None
        original_data_fim = config.data_fim if config.pk else None
        
        form = ConfiguracaoPeriodoInscricaoForm(request.POST, instance=config)
        if form.is_valid():
            saved_config = form.save(commit=False)
            if second_only and original_data_inicio and original_data_fim:
                # Force preserve regular period dates, making sure they cannot be edited
                saved_config.data_inicio = original_data_inicio
                saved_config.data_fim = original_data_fim
            saved_config.save()
            messages.success(request, "Configuração do período de inscrições salva com sucesso!")
            return redirect('admin_periodo_inscricao')
            
        return render(request, 'core/admin_periodo_inscricao.html', {
            'form': form, 
            'object': config if config.pk else None,
            'editing': True,
            'second_only': second_only,
            'status_inscricao': status_inscricao
        })


@login_required
def inscricao_segunda_chamada(request):
    if request.user.is_comissao:
        return redirect('dashboard')
        
    delegacao = request.user.delegacao_ativa
    inscricao = getattr(delegacao, 'inscricao', None)
    
    from django.utils import timezone
    from .models import ConfiguracaoPeriodoInscricao, SubstituicaoAtleta
    
    config = ConfiguracaoPeriodoInscricao.objects.first()
    now = timezone.now()
    is_segunda_chamada_active = config and config.segunda_chamada_inicio and config.segunda_chamada_fim and (config.segunda_chamada_inicio <= now <= config.segunda_chamada_fim)
    
    if not is_segunda_chamada_active:
        messages.error(request, "O período de segunda chamada de inscrições não está ativo.")
        return redirect('dashboard')
        
    if not inscricao:
        messages.error(request, "Sua delegação não possui uma inscrição ativa realizada no período regular.")
        return redirect('dashboard')
        
    modalidades_inscritas = [im.modalidade for im in inscricao.modalidades.all()]
    
    # Get current registered athletes
    atletas_atuais = list(inscricao.atletas_inscritos)
    
    # Get all athletes of this delegation
    todos_atletas = Atleta.objects.filter(cadastrado_por=delegacao)
    
    # Available athletes (not currently registered)
    atletas_disponiveis = [a for a in todos_atletas if a not in atletas_atuais]
    
    if request.method == 'POST':
        substitutions_to_create = []
        athletes_to_remove_ids = []
        athletes_to_add_ids = []
        
        # 1. Process substitutions
        sub_sai_list = request.POST.getlist('substituicao_sai[]') or request.POST.getlist('substituicao_sai')
        sub_entra_list = request.POST.getlist('substituicao_entra[]') or request.POST.getlist('substituicao_entra')
        
        for sai_str, entra_str in zip(sub_sai_list, sub_entra_list):
            if sai_str and entra_str:
                sai_id = int(sai_str)
                entra_id = int(entra_str)
                # Verify that the outgoing athlete is actually in the team
                if sai_id in [a.id for a in atletas_atuais] and entra_id in [a.id for a in todos_atletas]:
                    substitutions_to_create.append((sai_id, entra_id))
                    athletes_to_remove_ids.append(sai_id)
                    athletes_to_add_ids.append(entra_id)
                
        # 2. Process additions
        added_athlete_ids_str = request.POST.getlist('adicionar_atletas') or request.POST.getlist('adicionar_atletas[]')
        for aid_str in added_athlete_ids_str:
            aid = int(aid_str)
            if aid not in athletes_to_add_ids and aid not in [a.id for a in atletas_atuais]:
                athletes_to_add_ids.append(aid)
                
        # Calculate final list of athletes
        final_athlete_ids = [a.id for a in atletas_atuais if a.id not in athletes_to_remove_ids]
        for aid in athletes_to_add_ids:
            if aid not in final_athlete_ids:
                final_athlete_ids.append(aid)
                
        selected_atletas = Atleta.objects.filter(id__in=final_athlete_ids, cadastrado_por=delegacao)
        
        if not selected_atletas.exists():
            messages.error(request, "Por favor, selecione ao menos um atleta.")
            return redirect('inscricao_segunda_chamada')
            
        # Update database relation
        for im in inscricao.modalidades.all():
            im.atletas.set(selected_atletas)
            
        # Create SubstituicaoAtleta records
        for sai_id, entra_id in substitutions_to_create:
            sai = Atleta.objects.get(id=sai_id)
            entra = Atleta.objects.get(id=entra_id)
            SubstituicaoAtleta.objects.get_or_create(
                inscricao=inscricao,
                atleta_saiu=sai,
                atleta_entrou=entra
            )
            # Remove o atleta substituído de todas as modalidades e garante a inclusão do substituto
            for im in inscricao.modalidades.all():
                im.atletas.remove(sai)
                im.atletas.add(entra)

            # Atleta que saiu perde conformidade e status de deferido
            sai.em_conformidade = False
            sai.status_avaliacao = 'substituido'
            sai.justificativa_inconformidade = f"Substituído por {entra.nome_completo} na Segunda Chamada."
            sai.save(update_fields=['em_conformidade', 'status_avaliacao', 'justificativa_inconformidade'])

            # Atleta substituto assume a vaga com status deferido para entrar na pré-súmula
            entra.em_conformidade = True
            entra.status_avaliacao = 'deferido'
            entra.justificativa_inconformidade = ''
            entra.save(update_fields=['status_avaliacao', 'em_conformidade', 'justificativa_inconformidade'])

            # Atualiza pré-súmulas não finalizadas que continham o atleta substituído
            PreSumulaAtleta.objects.filter(
                presumula__jogo__finalizado=False,
                atleta=sai
            ).update(atleta=entra)

        # Identifica inclusões puras (atletas adicionados que não são substitutos)
        substituto_ids = {e for _, e in substitutions_to_create}
        standalone_added_ids = [aid for aid in athletes_to_add_ids if aid not in substituto_ids]

        # Reset evaluation status apenas para atletas recém-adicionados que não são substitutos
        for aid in standalone_added_ids:
            try:
                at_added = Atleta.objects.get(id=aid, cadastrado_por=delegacao)
                at_added.status_avaliacao = 'nao_avaliado'
                at_added.em_conformidade = False
                at_added.save(update_fields=['status_avaliacao', 'em_conformidade'])
            except Atleta.DoesNotExist:
                pass
            
        # Se houverem adições avulsas (não substituições), reavaliação é necessária
        if standalone_added_ids or delegacao.status_delegacao != 'deferido':
            inscricao.status = 'pendente'
            inscricao.save()
            delegacao.status_delegacao = 'pendente'
            delegacao.justificativa_delegacao = ''
            delegacao.save()
        
        # Notify commission
        comissao = User.objects.filter(role='COMISSAO')
        for admin in comissao:
            Notificacao.objects.create(
                usuario=admin,
                mensagem=f"Alteração de atletas na Segunda Chamada enviada pela delegação {delegacao.nome_delegacao or delegacao.email}.",
                link='/comissao/delegacoes/'
            )
            
        messages.success(request, "Alterações da Segunda Chamada enviadas com sucesso! A Comissão Organizadora fará a reavaliação.")
        return redirect('inscricao_detail')
        
    return render(request, 'core/inscricao_segunda_chamada.html', {
        'inscricao': inscricao,
        'modalidades': modalidades_inscritas,
        'atletas_atuais': atletas_atuais,
        'atletas_disponiveis': atletas_disponiveis,
        'todos_atletas': todos_atletas
    })


# =====================================================================
# Vistas do Módulo de Chaveamento (Comissão & Delegações)
# =====================================================================
from .models import ChaveamentoModalidade, GrupoChaveamento, TimeGrupo, PartidaChaveamento
from .chaveamento_services import (
    gerar_chaveamento_modalidade,
    registrar_resultado_partida,
    encerrar_fase_grupos_e_gerar_mata_mata,
    atualizar_tabela_grupo,
    atualizar_classificados_e_preencher_mata_mata,
    classificar_delegacoes_por_campus,
    obter_resumo_chaveamentos_admin,
    obter_resumo_chaveamentos_publico
)

class ChaveamentoAdminListView(LoginRequiredMixin, View):
    """
    Lista todas as modalidades com estatísticas de delegações por campus e status do chaveamento (Otimizado em lote).
    Disponível para a Comissão Organizadora.
    """
    def get(self, request):
        if not request.user.is_comissao:
            messages.error(request, "Acesso restrito à Comissão Organizadora.")
            return redirect('dashboard')

        modalidades_info = obter_resumo_chaveamentos_admin()

        return render(request, 'core/chaveamento_admin_list.html', {
            'modalidades_info': modalidades_info
        })


class ChaveamentoAdminDetailView(LoginRequiredMixin, View):
    """
    Painel de Gestão e Controle do Chaveamento de uma modalidade para a Comissão.
    """
    def get(self, request, pk):
        if not request.user.is_comissao:
            messages.error(request, "Acesso restrito à Comissão Organizadora.")
            return redirect('dashboard')

        modalidade = get_object_or_404(Modalidade, pk=pk)
        chaveamento = getattr(modalidade, 'chaveamento', None)

        if not chaveamento:
            messages.info(request, "O chaveamento para esta modalidade ainda não foi gerado. Clique em 'Gerar Chaveamento' para iniciar.")
            return redirect('chaveamento_admin_list')

        atualizar_classificados_e_preencher_mata_mata(chaveamento)

        grupos = chaveamento.grupos.prefetch_related('times__delegacao', 'partidas__time_a', 'partidas__time_b', 'partidas__vencedor', 'partidas__perdedor').all()
        partidas_mata_mata = chaveamento.partidas.filter(grupo__isnull=True).select_related('time_a', 'time_b', 'vencedor', 'perdedor', 'jogo').order_by('id')

        # Agrupa partidas por fase
        partidas_por_fase = {
            'QUARTAS_LOCAL': [],
            'SEMI_LOCAL': [],
            'FINAL_LOCAL': [],
            'DISPUTA_3_LOCAL': [],
            'SEMI_GERAL': [],
            'FINAL_GERAL': [],
            'BRONZE': [],
        }

        for p in partidas_mata_mata:
            if p.fase in partidas_por_fase:
                partidas_por_fase[p.fase].append(p)

        buckets = classificar_delegacoes_por_campus(modalidade)

        from core.disciplinar_services import obter_relatorio_disciplinar_modalidade
        relatorio_disciplinar = obter_relatorio_disciplinar_modalidade(modalidade)

        return render(request, 'core/chaveamento_admin_detail.html', {
            'modalidade': modalidade,
            'chaveamento': chaveamento,
            'grupos': grupos,
            'partidas_por_fase': partidas_por_fase,
            'buckets': buckets,
            'relatorio_disciplinar': relatorio_disciplinar
        })


@user_passes_test(lambda u: u.is_authenticated and (getattr(u, 'is_comissao', False) or u.is_staff or u.is_superuser))
def gerar_chaveamento_view(request, pk):
    if request.method == 'POST':
        modalidade = get_object_or_404(Modalidade, pk=pk)
        chaveamento = gerar_chaveamento_modalidade(modalidade)
        messages.success(request, f"Chaveamento da modalidade '{modalidade.nome}' gerado com sucesso!")
        return redirect('chaveamento_admin_detail', pk=modalidade.pk)
    return redirect('chaveamento_admin_list')


@user_passes_test(lambda u: u.is_authenticated and (getattr(u, 'is_comissao', False) or u.is_staff or u.is_superuser))
def encerrar_fase_grupos_view(request, pk):
    if request.method == 'POST':
        modalidade = get_object_or_404(Modalidade, pk=pk)
        chaveamento = get_object_or_404(ChaveamentoModalidade, modalidade=modalidade)
        encerrar_fase_grupos_e_gerar_mata_mata(chaveamento)
        messages.success(request, "Fase de grupos encerrada! Mata-mata local e fase geral construídos com sucesso!")
        return redirect('chaveamento_admin_detail', pk=modalidade.pk)
    return redirect('chaveamento_admin_list')


@user_passes_test(lambda u: u.is_authenticated and (getattr(u, 'is_comissao', False) or u.is_staff or u.is_superuser))
def resetar_chaveamento_view(request, pk):
    if request.method == 'POST':
        modalidade = get_object_or_404(Modalidade, pk=pk)
        chaveamentos = ChaveamentoModalidade.objects.filter(modalidade=modalidade)
        for ch in chaveamentos:
            jogos_ids = list(ch.partidas.filter(jogo__isnull=False).values_list('jogo_id', flat=True))
            if jogos_ids:
                Jogo.objects.filter(id__in=jogos_ids).delete()
        chaveamentos.delete()
        messages.warning(request, f"Chaveamento da modalidade '{modalidade.nome}' resetado com sucesso.")
    return redirect('chaveamento_admin_list')


@user_passes_test(lambda u: u.is_authenticated and (getattr(u, 'is_comissao', False) or u.is_staff or u.is_superuser))
def salvar_resultado_partida_view(request, pk):
    if request.method == 'POST':
        partida = get_object_or_404(PartidaChaveamento, pk=pk)
        placar_a_raw = request.POST.get('placar_a')
        placar_b_raw = request.POST.get('placar_b')
        wo_tipo = request.POST.get('wo_tipo', '').strip()
        motivo_wo = request.POST.get('motivo_wo', '').strip()
        data_raw = request.POST.get('data_jogo') or request.POST.get('data_partida')
        horario_raw = request.POST.get('horario_jogo') or request.POST.get('horario_partida')

        updated_anything = False

        if wo_tipo in ['TIME_A', 'TIME_B', 'AMBOS']:
            try:
                placar_a = int(placar_a_raw) if (placar_a_raw is not None and placar_a_raw != '') else None
                placar_b = int(placar_b_raw) if (placar_b_raw is not None and placar_b_raw != '') else None
                registrar_resultado_partida(partida, placar_a, placar_b, wo_tipo=wo_tipo, motivo_wo=motivo_wo)
                updated_anything = True
            except ValueError:
                messages.error(request, "Placares inválidos para W.O.")
        elif placar_a_raw is not None and placar_b_raw is not None and placar_a_raw != '' and placar_b_raw != '':
            try:
                placar_a = int(placar_a_raw)
                placar_b = int(placar_b_raw)
                registrar_resultado_partida(partida, placar_a, placar_b, wo_tipo='', motivo_wo='')
                updated_anything = True
            except ValueError:
                messages.error(request, "Placares inválidos.")
        elif partida.wo_tipo and wo_tipo == '':
            partida.wo_tipo = ''
            partida.motivo_wo = ''
            partida.finalizada = False
            partida.placar_a = None
            partida.placar_b = None
            partida.vencedor = None
            partida.perdedor = None
            partida.save()
            if partida.jogo:
                partida.jogo.wo_tipo = ''
                partida.jogo.motivo_wo = ''
                partida.jogo.placar_time_a = None
                partida.jogo.placar_time_b = None
                partida.jogo.finalizado = False
                partida.jogo.save()
            if partida.grupo:
                atualizar_tabela_grupo(partida.grupo)
                atualizar_classificados_e_preencher_mata_mata(partida.chaveamento)
            updated_anything = True

        import datetime
        if data_raw:
            try:
                partida.data_partida = datetime.datetime.strptime(data_raw, '%Y-%m-%d').date()
                if partida.jogo:
                    partida.jogo.data_jogo = partida.data_partida
                    partida.jogo.save()
                updated_anything = True
            except ValueError:
                pass

        if horario_raw:
            try:
                partida.horario_partida = datetime.datetime.strptime(horario_raw, '%H:%M').time()
                if partida.jogo:
                    partida.jogo.horario_jogo = partida.horario_partida
                    partida.jogo.save()
                updated_anything = True
            except ValueError:
                pass

        partida.save()

        if updated_anything:
            messages.success(request, "Dados da partida salvos com sucesso!")

        return redirect('chaveamento_admin_detail', pk=partida.chaveamento.modalidade.pk)
    return redirect('chaveamento_admin_list')


@user_passes_test(lambda u: u.is_authenticated and (getattr(u, 'is_comissao', False) or u.is_staff or u.is_superuser))
def salvar_fase_data_view(request, pk):
    if request.method == 'POST':
        chaveamento = get_object_or_404(ChaveamentoModalidade, pk=pk)
        fase_key = request.POST.get('fase_key')
        data_fase_raw = request.POST.get('data_fase')

        if fase_key:
            datas = dict(chaveamento.datas_fases) if isinstance(chaveamento.datas_fases, dict) else {}
            datas[fase_key] = data_fase_raw
            chaveamento.datas_fases = datas
            chaveamento.save()
            messages.success(request, "Data da fase salva com sucesso!")

        return redirect('chaveamento_admin_detail', pk=chaveamento.modalidade.pk)
    return redirect('chaveamento_admin_list')


@user_passes_test(lambda u: u.is_authenticated and (getattr(u, 'is_comissao', False) or u.is_staff or u.is_superuser))
def salvar_cartao_partida_view(request, pk):
    """
    Registra um cartão para um atleta em uma partida (suporta POST normal e AJAX).
    """
    if request.method == 'POST':
        partida = get_object_or_404(PartidaChaveamento, pk=pk)
        atleta_id = request.POST.get('atleta_id')
        tipo_cartao = request.POST.get('tipo_cartao')
        observacao = request.POST.get('observacao', '').strip()

        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')

        if atleta_id and tipo_cartao:
            atleta = get_object_or_404(Atleta, pk=atleta_id)
            try:
                from core.disciplinar_services import registrar_cartao_atleta
                cartao = registrar_cartao_atleta(partida, atleta, tipo_cartao, observacao=observacao)
                if is_ajax:
                    cartoes_list = [
                        {
                            'id': c.id,
                            'atleta_nome': c.atleta.nome_completo,
                            'delegacao_nome': (c.delegacao.nome_delegacao or c.delegacao.email) if c.delegacao else '',
                            'tipo': c.tipo,
                            'tipo_display': c.get_tipo_display()
                        }
                        for c in partida.cartoes.all().select_related('atleta', 'delegacao')
                    ]
                    return JsonResponse({'success': True, 'cartoes': cartoes_list})

                messages.success(request, f"Cartão {cartao.get_tipo_display()} registrado para {atleta.nome_completo} com sucesso!")
            except Exception as e:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': str(e)}, status=400)
                messages.error(request, f"Erro ao registrar cartão: {str(e)}")
        else:
            if is_ajax:
                return JsonResponse({'success': False, 'error': 'Selecione o atleta e o tipo de cartão.'}, status=400)
            messages.error(request, "Selecione o atleta e o tipo de cartão.")

        return redirect('chaveamento_admin_detail', pk=partida.chaveamento.modalidade.pk)
    return redirect('chaveamento_admin_list')


@user_passes_test(lambda u: u.is_authenticated and (getattr(u, 'is_comissao', False) or u.is_staff or u.is_superuser))
def remover_cartao_partida_view(request, pk):
    """
    Remove um cartão aplicado a um atleta (suporta POST normal e AJAX).
    """
    if request.method == 'POST':
        from core.disciplinar_services import remover_cartao_atleta
        from core.models import CartaoPartida
        cartao = get_object_or_404(CartaoPartida, pk=pk)
        partida = cartao.partida
        modalidade_pk = cartao.modalidade.pk if cartao.modalidade else (partida.chaveamento.modalidade.pk if partida and partida.chaveamento else None)
        remover_cartao_atleta(pk)

        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')
        if is_ajax:
            cartoes_list = []
            if partida:
                cartoes_list = [
                    {
                        'id': c.id,
                        'atleta_nome': c.atleta.nome_completo,
                        'delegacao_nome': (c.delegacao.nome_delegacao or c.delegacao.email) if c.delegacao else '',
                        'tipo': c.tipo,
                        'tipo_display': c.get_tipo_display()
                    }
                    for c in partida.cartoes.all().select_related('atleta', 'delegacao')
                ]
            return JsonResponse({'success': True, 'cartoes': cartoes_list})

        messages.success(request, "Cartão removido com sucesso!")
        if modalidade_pk:
            return redirect('chaveamento_admin_detail', pk=modalidade_pk)
        return redirect('chaveamento_admin_list')
    return redirect('chaveamento_admin_list')


class ChaveamentoPublicListView(LoginRequiredMixin, View):
    """
    Lista de Chaveamentos acessível para Representantes de Delegações e membros (Otimizado em lote).
    """
    def get(self, request):
        delegacao_user = request.user.delegacao_ativa
        modalidades_info = obter_resumo_chaveamentos_publico(delegacao_user)

        return render(request, 'core/chaveamento_public_list.html', {
            'modalidades_info': modalidades_info,
            'delegacao': delegacao_user
        })


class ChaveamentoPublicDetailView(LoginRequiredMixin, View):
    """
    Visualização pública e intuitiva do Chaveamento para Delegações.
    """
    def get(self, request, pk):
        modalidade = get_object_or_404(Modalidade, pk=pk)
        chaveamento = getattr(modalidade, 'chaveamento', None)

        if not chaveamento:
            messages.info(request, "O chaveamento desta modalidade ainda não foi gerado pela Comissão Organizadora.")
            return redirect('chaveamento_public_list')

        atualizar_classificados_e_preencher_mata_mata(chaveamento)

        grupos = chaveamento.grupos.prefetch_related('times__delegacao', 'partidas__time_a', 'partidas__time_b', 'partidas__vencedor', 'partidas__perdedor').all()
        partidas_mata_mata = chaveamento.partidas.filter(grupo__isnull=True).select_related('time_a', 'time_b', 'vencedor', 'perdedor', 'jogo').order_by('id')

        partidas_por_fase = {
            'QUARTAS_LOCAL': [],
            'SEMI_LOCAL': [],
            'FINAL_LOCAL': [],
            'DISPUTA_3_LOCAL': [],
            'SEMI_GERAL': [],
            'FINAL_GERAL': [],
            'BRONZE': [],
        }

        for p in partidas_mata_mata:
            if p.fase in partidas_por_fase:
                partidas_por_fase[p.fase].append(p)

        delegacao_user = request.user.delegacao_ativa

        from core.disciplinar_services import obter_relatorio_disciplinar_modalidade
        relatorio_disciplinar = obter_relatorio_disciplinar_modalidade(modalidade)

        return render(request, 'core/chaveamento_public_detail.html', {
            'modalidade': modalidade,
            'chaveamento': chaveamento,
            'grupos': grupos,
            'partidas_por_fase': partidas_por_fase,
            'delegacao': delegacao_user,
            'relatorio_disciplinar': relatorio_disciplinar
        })


def chaveamento_share_list_view(request):
    """
    Visualização pública e independente de todas as modalidades para compartilhamento externo.
    Não exige login e permite que o público escolha qual modalidade consultar.
    """
    modalidades_info = obter_resumo_chaveamentos_publico(None)
    return render(request, 'core/chaveamento_share_list.html', {
        'modalidades_info': modalidades_info,
    })


def chaveamento_share_view(request, pk):
    """
    Visualização pública e independente para compartilhamento externo do Chaveamento de uma modalidade.
    Não exibe menu lateral nem barras de navegação do sistema para evitar sensação de layout quebrado.
    """
    modalidade = get_object_or_404(Modalidade, pk=pk)
    chaveamento = getattr(modalidade, 'chaveamento', None)

    if not chaveamento:
        messages.info(request, "O chaveamento desta modalidade ainda não foi gerado.")
        return redirect('chaveamento_share_list')

    atualizar_classificados_e_preencher_mata_mata(chaveamento)

    grupos = chaveamento.grupos.prefetch_related('times__delegacao', 'partidas__time_a', 'partidas__time_b', 'partidas__vencedor', 'partidas__perdedor').all()
    partidas_mata_mata = chaveamento.partidas.filter(grupo__isnull=True).select_related('time_a', 'time_b', 'vencedor', 'perdedor', 'jogo').order_by('id')

    partidas_por_fase = {
        'QUARTAS_LOCAL': [],
        'SEMI_LOCAL': [],
        'FINAL_LOCAL': [],
        'DISPUTA_3_LOCAL': [],
        'SEMI_GERAL': [],
        'FINAL_GERAL': [],
        'BRONZE': [],
    }

    for p in partidas_mata_mata:
        if p.fase in partidas_por_fase:
            partidas_por_fase[p.fase].append(p)

    return render(request, 'core/chaveamento_share.html', {
        'modalidade': modalidade,
        'chaveamento': chaveamento,
        'grupos': grupos,
        'partidas_por_fase': partidas_por_fase,
    })


class ChaveamentoJogosListaView(View):
    """
    Lista todos os jogos do chaveamento em formato cronológico
    agrupados por data/dia. Acessível publicamente (sem login) e integrado ao painel
    para Comissão e Delegações.
    """
    def get(self, request, is_public_route=False):
        is_public = is_public_route or (not request.user.is_authenticated) or (request.GET.get('public') == '1')
        base_template = 'core/chaveamento_share_base.html' if is_public else 'base.html'

        # Determina URL para voltar
        if not is_public:
            if getattr(request.user, 'is_comissao', False) or request.user.is_staff:
                voltar_url = reverse('chaveamento_admin_list')
            else:
                voltar_url = reverse('chaveamento_public_list')
        else:
            voltar_url = reverse('chaveamento_share_list')

        # 1. Busca todas as partidas de chaveamento
        partidas_qs = PartidaChaveamento.objects.select_related(
            'chaveamento__modalidade',
            'grupo',
            'time_a',
            'time_b',
            'vencedor',
            'jogo'
        ).all()

        # 2. Busca jogos avulsos sem partida de chaveamento vinculada
        jogos_avulsos_qs = Jogo.objects.filter(
            partida_chaveamento__isnull=True
        ).select_related('modalidade', 'time_a', 'time_b').all()

        import datetime
        DIAS_SEMANA = [
            'Segunda-feira', 'Terça-feira', 'Quarta-feira',
            'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo'
        ]

        def formatar_time_display_local(time_obj, partida, posicao='a'):
            if time_obj:
                return time_obj.nome_delegacao or time_obj.nome_completo or time_obj.email
            fase = partida.fase if partida else ''
            if fase == 'QUARTAS_LOCAL':
                return f"A definir (Quartas - Time {posicao.upper()})"
            elif fase in ['SEMI_LOCAL', 'SEMI_GERAL']:
                return f"A definir (Semi - Time {posicao.upper()})"
            elif fase in ['FINAL_LOCAL', 'FINAL_GERAL']:
                return f"A definir (Final - Time {posicao.upper()})"
            elif fase in ['DISPUTA_3_LOCAL', 'BRONZE']:
                return f"A definir (3º Lugar - Time {posicao.upper()})"
            elif fase == 'EXTERNO_ELIMINATORIA':
                return f"A definir (Eliminatória - Time {posicao.upper()})"
            return f"A definir (Time {posicao.upper()})"

        todos_jogos = []

        for p in partidas_qs:
            mod = p.modalidade
            if not mod:
                continue

            # Data
            data = p.data_partida
            if not data and p.jogo and p.jogo.data_jogo:
                data = p.jogo.data_jogo
            if not data and p.chaveamento and getattr(p.chaveamento, 'datas_fases', None):
                df = p.chaveamento.datas_fases.get(p.fase)
                if df:
                    try:
                        data = datetime.datetime.strptime(df, '%Y-%m-%d').date()
                    except ValueError:
                        pass

            # Horário
            horario = p.horario_partida
            if not horario and p.jogo and p.jogo.horario_jogo:
                horario = p.jogo.horario_jogo

            # Local
            local = None
            if p.jogo and p.jogo.local:
                local = p.jogo.local
            if not local:
                local = "Local a definir"

            # URL do chaveamento correspondente
            chaveamento_url = None
            if mod:
                if not is_public and (getattr(request.user, 'is_comissao', False) or request.user.is_staff):
                    chaveamento_url = reverse('chaveamento_admin_detail', kwargs={'pk': mod.pk})
                elif not is_public:
                    chaveamento_url = reverse('chaveamento_public_detail', kwargs={'pk': mod.pk})
                else:
                    chaveamento_url = reverse('chaveamento_share', kwargs={'pk': mod.pk})

            todos_jogos.append({
                'id': f"P-{p.id}",
                'pk': p.id,
                'modalidade': mod,
                'fase_display': p.get_fase_display(),
                'grupo_display': p.grupo.nome if p.grupo else '',
                'rodada': p.rodada,
                'time_a': p.time_a,
                'time_a_nome': formatar_time_display_local(p.time_a, p, 'a'),
                'time_b': p.time_b,
                'time_b_nome': formatar_time_display_local(p.time_b, p, 'b'),
                'data': data,
                'data_exibicao': data.strftime('%d/%m/%Y') if data else 'A definir',
                'horario': horario,
                'horario_exibicao': horario.strftime('%H:%M') if horario else 'A definir',
                'local': local,
                'placar_a': p.placar_a,
                'placar_b': p.placar_b,
                'finalizada': p.finalizada,
                'wo_tipo': p.wo_tipo,
                'motivo_wo': p.motivo_wo,
                'is_wo': p.is_wo,
                'is_wo_time_a': p.is_wo_time_a,
                'is_wo_time_b': p.is_wo_time_b,
                'is_wo_duplo': p.is_wo_duplo,
                'vencedor': p.vencedor,
                'chaveamento_url': chaveamento_url,
            })

        for j in jogos_avulsos_qs:
            mod = j.modalidade
            if not mod:
                continue

            chaveamento_url = None
            if hasattr(mod, 'chaveamento'):
                if not is_public and (getattr(request.user, 'is_comissao', False) or request.user.is_staff):
                    chaveamento_url = reverse('chaveamento_admin_detail', kwargs={'pk': mod.pk})
                elif not is_public:
                    chaveamento_url = reverse('chaveamento_public_detail', kwargs={'pk': mod.pk})
                else:
                    chaveamento_url = reverse('chaveamento_share', kwargs={'pk': mod.pk})

            ta_nome = j.time_a.nome_delegacao or j.time_a.nome_completo or j.time_a.email if j.time_a else "A definir"
            tb_nome = j.time_b.nome_delegacao or j.time_b.nome_completo or j.time_b.email if j.time_b else "A definir"

            todos_jogos.append({
                'id': f"J-{j.id}",
                'pk': j.id,
                'modalidade': mod,
                'fase_display': 'Partida Geral',
                'grupo_display': '',
                'rodada': None,
                'time_a': j.time_a,
                'time_a_nome': ta_nome,
                'time_b': j.time_b,
                'time_b_nome': tb_nome,
                'data': j.data_jogo,
                'data_exibicao': j.data_jogo.strftime('%d/%m/%Y') if j.data_jogo else 'A definir',
                'horario': j.horario_jogo,
                'horario_exibicao': j.horario_jogo.strftime('%H:%M') if j.horario_jogo else 'A definir',
                'local': j.local or "Local a definir",
                'placar_a': j.placar_time_a,
                'placar_b': j.placar_time_b,
                'finalizada': j.finalizado,
                'wo_tipo': j.wo_tipo,
                'motivo_wo': j.motivo_wo,
                'is_wo': j.is_wo,
                'is_wo_time_a': j.is_wo_time_a,
                'is_wo_time_b': j.is_wo_time_b,
                'is_wo_duplo': j.is_wo_duplo,
                'vencedor': None,
                'chaveamento_url': chaveamento_url,
            })

        # Ordenação cronológica global
        def sort_key(item):
            has_date = 0 if item['data'] is not None else 1
            d = item['data'] or datetime.date.max
            has_time = 0 if item['horario'] is not None else 1
            h = item['horario'] or datetime.time.max
            m_nome = item['modalidade'].nome if item['modalidade'] else ''
            return (has_date, d, has_time, h, m_nome, item['id'])

        todos_jogos.sort(key=sort_key)

        from collections import OrderedDict
        grupos_dias_dict = OrderedDict()
        modalidades_encontradas = {}

        for j in todos_jogos:
            d = j['data']
            if d not in grupos_dias_dict:
                grupos_dias_dict[d] = []
            grupos_dias_dict[d].append(j)

            if j['modalidade']:
                modalidades_encontradas[j['modalidade'].pk] = j['modalidade']

        grupos_dias = []
        for d, jogos_do_dia in grupos_dias_dict.items():
            if d is not None:
                dia_semana = DIAS_SEMANA[d.weekday()]
                label = f"{d.strftime('%d/%m/%Y')} • {dia_semana}"
                data_iso = d.strftime('%Y-%m-%d')
                data_curta = d.strftime('%d/%m')
            else:
                dia_semana = ''
                label = "Data a Definir"
                data_iso = "indefinido"
                data_curta = "A definir"

            grupos_dias.append({
                'data': d,
                'data_iso': data_iso,
                'data_curta': data_curta,
                'dia_semana': dia_semana,
                'label': label,
                'is_indefinido': d is None,
                'total_jogos': len(jogos_do_dia),
                'jogos': jogos_do_dia
            })

        total_jogos = len(todos_jogos)
        total_finalizados = sum(1 for j in todos_jogos if j['finalizada'] or j['is_wo'])
        total_pendentes = total_jogos - total_finalizados

        return render(request, 'core/chaveamento_jogos_lista.html', {
            'base_template': base_template,
            'is_public': is_public,
            'voltar_url': voltar_url,
            'grupos_dias': grupos_dias,
            'modalidades_lista': sorted(modalidades_encontradas.values(), key=lambda m: m.nome),
            'total_jogos': total_jogos,
            'total_finalizados': total_finalizados,
            'total_pendentes': total_pendentes,
            'total_dias': len([g for g in grupos_dias if not g['is_indefinido']]),
        })





