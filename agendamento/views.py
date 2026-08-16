from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from datetime import datetime, date, time

from django.db.models import Q

from core.models import Modalidade, PartidaChaveamento, Jogo
from .models import (
    ConfiguracaoGeral, DataDisponivel, RecursoLocal,
    ParametroModalidade, RestricaoFase, CenarioExecucao, ItemAlocacao
)
from .forms import (
    ConfiguracaoGeralForm, DataDisponivelForm, RecursoLocalForm,
    RestricaoFaseForm, ParametroModalidadeForm
)
from .services import (
    obter_ou_criar_configuracao, executar_agendamento,
    aplicar_cenario_ao_oficial, resetar_todos_horarios,
    FASE_NOMES_PADRAO, FASE_ORDEM_PADRAO
)


def _is_comissao_or_admin(user):
    return user.is_authenticated and (getattr(user, 'is_comissao', False) or user.is_staff or user.is_superuser)


@user_passes_test(_is_comissao_or_admin)
def dashboard_agendamento_view(request):
    """
    Painel central do módulo de automação de horários e agendamento.
    """
    configuracao = obter_ou_criar_configuracao()
    datas_count = configuracao.datas.filter(ativo=True).count()
    recursos_count = configuracao.recursos.filter(ativo=True).count()
    fases_count = configuracao.restricoes_fases.count()
    
    partidas_pendentes = PartidaChaveamento.objects.filter(finalizada=False).exclude(chaveamento__modalidade__nome__icontains='atletismo').count()
    cenarios = configuracao.cenarios.all()[:8]

    # Verifica se existem partidas com horários já atribuídos ou simulações geradas
    tem_jogos_gerados = PartidaChaveamento.objects.filter(finalizada=False).filter(
        Q(data_partida__isnull=False) | Q(horario_partida__isnull=False)
    ).exists() or configuracao.cenarios.exists()

    context = {
        'configuracao': configuracao,
        'datas_count': datas_count,
        'recursos_count': recursos_count,
        'fases_count': fases_count,
        'partidas_pendentes': partidas_pendentes,
        'cenarios': cenarios,
        'tem_jogos_gerados': tem_jogos_gerados,
    }
    return render(request, 'agendamento/dashboard.html', context)


@user_passes_test(_is_comissao_or_admin)
def resetar_horarios_view(request):
    """
    Limpa as datas, horários e quadras de todas as partidas pendentes do torneio.
    """
    if request.method == 'POST':
        configuracao = obter_ou_criar_configuracao()
        total_resetadas = resetar_todos_horarios(configuracao)
        messages.success(request, f"Todos os horários e locais foram resetados com sucesso ({total_resetadas} partidas atualizadas)!")
    return redirect('agendamento_dashboard')


@user_passes_test(_is_comissao_or_admin)
def datas_list_view(request):
    """
    Gerenciamento de datas gerais disponíveis da competição.
    """
    configuracao = obter_ou_criar_configuracao()
    datas = configuracao.datas.all().order_by('data')

    if request.method == 'POST':
        form = DataDisponivelForm(request.POST)
        if form.is_valid():
            nova_data = form.save(commit=False)
            nova_data.configuracao = configuracao
            try:
                nova_data.save()
                messages.success(request, f"Data {nova_data.data.strftime('%d/%m/%Y')} adicionada com sucesso!")
                return redirect('agendamento_datas')
            except Exception as e:
                messages.error(request, f"Erro ao salvar data: {str(e)}")
    else:
        form = DataDisponivelForm()

    context = {
        'configuracao': configuracao,
        'datas': datas,
        'form': form,
    }
    return render(request, 'agendamento/configuracao_datas.html', context)


@user_passes_test(_is_comissao_or_admin)
def data_edit_view(request, pk):
    """
    Atualiza uma data da competição via modal pop-up.
    """
    data_obj = get_object_or_404(DataDisponivel, pk=pk)
    if request.method == 'POST':
        form = DataDisponivelForm(request.POST, instance=data_obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"Data {data_obj.data.strftime('%d/%m/%Y')} atualizada com sucesso!")
        else:
            messages.error(request, "Dados inválidos ao editar data.")
    return redirect('agendamento_datas')


@user_passes_test(_is_comissao_or_admin)
def data_delete_view(request, pk):
    data_obj = get_object_or_404(DataDisponivel, pk=pk)
    data_str = data_obj.data.strftime('%d/%m/%Y')
    data_obj.delete()
    messages.success(request, f"Data {data_str} removida com sucesso!")
    return redirect('agendamento_datas')


@user_passes_test(_is_comissao_or_admin)
def recursos_list_view(request):
    """
    Gerenciamento de locais/quadras de jogos.
    """
    configuracao = obter_ou_criar_configuracao()
    recursos = configuracao.recursos.prefetch_related('modalidades_permitidas').order_by('ordem', 'nome')

    if request.method == 'POST':
        form = RecursoLocalForm(request.POST)
        if form.is_valid():
            novo_rec = form.save(commit=False)
            novo_rec.configuracao = configuracao
            novo_rec.save()
            form.save_m2m()
            messages.success(request, f"Local '{novo_rec.nome}' cadastrado com sucesso!")
            return redirect('agendamento_recursos')
    else:
        form = RecursoLocalForm()

    context = {
        'configuracao': configuracao,
        'recursos': recursos,
        'form': form,
    }
    return render(request, 'agendamento/configuracao_recursos.html', context)


@user_passes_test(_is_comissao_or_admin)
def recurso_edit_view(request, pk):
    recurso = get_object_or_404(RecursoLocal, pk=pk)
    if request.method == 'POST':
        form = RecursoLocalForm(request.POST, instance=recurso)
        if form.is_valid():
            form.save()
            messages.success(request, f"Local '{recurso.nome}' atualizado com sucesso!")
            return redirect('agendamento_recursos')
    else:
        form = RecursoLocalForm(instance=recurso)

    return render(request, 'agendamento/recurso_form_modal.html', {'form': form, 'recurso': recurso})


@user_passes_test(_is_comissao_or_admin)
def recurso_delete_view(request, pk):
    recurso = get_object_or_404(RecursoLocal, pk=pk)
    nome = recurso.nome
    recurso.delete()
    messages.success(request, f"Local '{nome}' removido com sucesso!")
    return redirect('agendamento_recursos')


@user_passes_test(_is_comissao_or_admin)
def fases_config_view(request):
    """
    Configuração genérica de restrição de datas por fase da competição.
    Permite definir para qualquer fase quais datas são permitidas.
    """
    configuracao = obter_ou_criar_configuracao()
    datas_disponiveis = configuracao.datas.filter(ativo=True).order_by('data')
    restricoes = configuracao.restricoes_fases.prefetch_related('datas_permitidas', 'modalidade').order_by('ordem_precedencia', 'fase_codigo')

    if request.method == 'POST':
        # Salva as restrições de cada fase via formulário matricial
        for rest in restricoes:
            datas_selecionadas_ids = request.POST.getlist(f'fase_datas_{rest.id}')
            rest.datas_permitidas.set(datas_selecionadas_ids)
            
            nome_custom = request.POST.get(f'fase_nome_{rest.id}', '').strip()
            if nome_custom:
                rest.fase_nome = nome_custom
                rest.save()

        messages.success(request, "Restrições de datas por fase salvas com sucesso!")
        return redirect('agendamento_fases')

    context = {
        'configuracao': configuracao,
        'datas_disponiveis': datas_disponiveis,
        'restricoes': restricoes,
    }
    return render(request, 'agendamento/configuracao_fases.html', context)


@user_passes_test(_is_comissao_or_admin)
def fase_create_view(request):
    """
    Adiciona uma nova restrição de fase genérica/personalizada.
    """
    configuracao = obter_ou_criar_configuracao()
    if request.method == 'POST':
        form = RestricaoFaseForm(request.POST, configuracao=configuracao)
        if form.is_valid():
            nova_fase = form.save(commit=False)
            nova_fase.configuracao = configuracao
            nova_fase.save()
            form.save_m2m()
            messages.success(request, f"Restrição para fase '{nova_fase.fase_nome or nova_fase.fase_codigo}' criada com sucesso!")
            return redirect('agendamento_fases')
    else:
        form = RestricaoFaseForm(configuracao=configuracao)

    return render(request, 'agendamento/fase_form.html', {'form': form, 'configuracao': configuracao})


@user_passes_test(_is_comissao_or_admin)
def fase_delete_view(request, pk):
    restricao = get_object_or_404(RestricaoFase, pk=pk)
    nome = restricao.fase_nome or restricao.fase_codigo
    restricao.delete()
    messages.success(request, f"Restrição da fase '{nome}' removida!")
    return redirect('agendamento_fases')


@user_passes_test(_is_comissao_or_admin)
def regras_config_view(request):
    """
    Configurações globais de tempos, descansos e parâmetros por modalidade.
    """
    configuracao = obter_ou_criar_configuracao()
    parametros = configuracao.parametros_modalidades.exclude(modalidade__nome__icontains='atletismo').select_related('modalidade').order_by('modalidade__nome', 'modalidade__genero')

    if request.method == 'POST':
        form = ConfiguracaoGeralForm(request.POST, instance=configuracao)
        if form.is_valid():
            form.save()

            # Salva parâmetros individuais das modalidades
            for param in parametros:
                dur_raw = request.POST.get(f'duracao_{param.id}')
                buff_raw = request.POST.get(f'buffer_{param.id}')
                if dur_raw:
                    try:
                        param.duracao_minutos = max(5, int(dur_raw))
                    except ValueError:
                        pass
                if buff_raw:
                    try:
                        param.intervalo_pos_jogo_minutos = max(0, int(buff_raw))
                    except ValueError:
                        pass
                param.save()

            messages.success(request, "Regras e parâmetros de agendamento atualizados com sucesso!")
            return redirect('agendamento_regras')
    else:
        form = ConfiguracaoGeralForm(instance=configuracao)

    context = {
        'configuracao': configuracao,
        'form': form,
        'parametros': parametros,
    }
    return render(request, 'agendamento/configuracao_regras.html', context)


@user_passes_test(_is_comissao_or_admin)
def gerar_cronograma_view(request):
    """
    Tela de acionamento do gerador automático de horários.
    """
    configuracao = obter_ou_criar_configuracao()
    modalidades = Modalidade.objects.exclude(nome__icontains='atletismo').order_by('nome', 'genero')
    total_partidas = PartidaChaveamento.objects.filter(finalizada=False).exclude(chaveamento__modalidade__nome__icontains='atletismo').count()

    if request.method == 'POST':
        titulo = request.POST.get('titulo', '').strip()
        modalidades_selecionadas = request.POST.getlist('modalidades')
        mod_ids = [int(m) for m in modalidades_selecionadas if m.isdigit()] if modalidades_selecionadas else None

        cenario = executar_agendamento(
            configuracao=configuracao,
            modalidades_ids=mod_ids,
            titulo=titulo or None
        )

        if cenario.status == 'sucesso':
            messages.success(request, f"Cronograma '{cenario.titulo}' gerado com sucesso!")
        else:
            messages.warning(request, "O cronograma foi processado, mas encontrou restrições que precisam de ajuste.")

        return redirect('agendamento_cenario_detalhe', pk=cenario.pk)

    context = {
        'configuracao': configuracao,
        'modalidades': modalidades,
        'total_partidas': total_partidas,
    }
    return render(request, 'agendamento/gerar_cronograma.html', context)


@user_passes_test(_is_comissao_or_admin)
def cenario_detalhe_view(request, pk):
    """
    Exibe a timeline detalhada, tabela por quadras/dias e diagnóstico do cenário.
    """
    cenario = get_object_or_404(CenarioExecucao, pk=pk)
    alocacoes = cenario.alocacoes.all().order_by('data_alocada', 'horario_inicio', 'recurso_nome')

    # Agrupamento por Data
    datas_agrupadas = {}
    for a in alocacoes:
        d_key = a.data_alocada
        if d_key not in datas_agrupadas:
            datas_agrupadas[d_key] = []
        datas_agrupadas[d_key].append(a)

    context = {
        'cenario': cenario,
        'alocacoes': alocacoes,
        'datas_agrupadas': datas_agrupadas,
        'total_alocacoes': alocacoes.count(),
    }
    return render(request, 'agendamento/resultado_cronograma.html', context)


@user_passes_test(_is_comissao_or_admin)
def aplicar_cenario_view(request, pk):
    """
    Aplica as datas, horários e locais gerados pelo cenário às partidas reais do torneio.
    """
    if request.method == 'POST':
        cenario = get_object_or_404(CenarioExecucao, pk=pk)
        try:
            total, msgs = aplicar_cenario_ao_oficial(cenario)
            for m in msgs:
                messages.success(request, m)
        except Exception as e:
            messages.error(request, f"Erro ao aplicar cronograma: {str(e)}")

        return redirect('agendamento_cenario_detalhe', pk=cenario.pk)
    return redirect('agendamento_dashboard')


@user_passes_test(_is_comissao_or_admin)
def cenario_delete_view(request, pk):
    cenario = get_object_or_404(CenarioExecucao, pk=pk)
    titulo = cenario.titulo
    cenario.delete()
    messages.success(request, f"Cenário '{titulo}' excluído!")
    return redirect('agendamento_dashboard')
