from datetime import datetime, date, time
from typing import List, Dict, Set, Optional, Tuple, Any
from django.db import transaction
from django.utils import timezone

from core.models import Modalidade, PartidaChaveamento, Jogo, ChaveamentoModalidade
from .models import (
    ConfiguracaoGeral, DataDisponivel, RecursoLocal, ParametroModalidade,
    RestricaoFase, CenarioExecucao, ItemAlocacao
)
from .engine import (
    DayWindow, ResourceConfig, ModalityParam, PhaseConstraint,
    MatchRequest, AllocatedSlot, DiagnosticIssue, EngineResult,
    ScheduleSolver, DiagnosticsFormatter
)


# Mapeamento de ordem lógica de fases padrão do sistema (apenas jogos em Diamantina)
FASE_ORDEM_PADRAO = {
    'GRUPO_LOCAL': 1,
    'QUARTAS_LOCAL': 2,
    'SEMI_LOCAL': 3,
    'FINAL_LOCAL': 4,
    'DISPUTA_3_LOCAL': 4,
    'SEMI_GERAL': 5,
    'FINAL_GERAL': 6,
    'BRONZE': 6,
}

FASE_NOMES_PADRAO = {
    'GRUPO_LOCAL': 'Fase de Grupos',
    'QUARTAS_LOCAL': 'Quartas de Final (Diamantina)',
    'SEMI_LOCAL': 'Semifinal (Diamantina)',
    'FINAL_LOCAL': 'Final (Diamantina)',
    'DISPUTA_3_LOCAL': '3º Lugar (Diamantina)',
    'SEMI_GERAL': 'Semifinal Geral',
    'FINAL_GERAL': 'Final Geral',
    'BRONZE': 'Chave Bronze (3º Lugar Geral)',
}


def obter_ou_criar_configuracao() -> ConfiguracaoGeral:
    """
    Recupera a configuração ativa ou cria uma configuração padrão com parâmetros
    e restrições de fases iniciais caso não existam.
    """
    config = ConfiguracaoGeral.objects.filter(ativo=True).first()
    if not config:
        config = ConfiguracaoGeral.objects.create(
            nome="Configuração Geral das Olimpíadas",
            ativo=True,
            intervalo_padrao_minutos=10,
            descanso_minimo_equipe_minutos=60,
            duracao_padrao_jogo_minutos=50
        )

    # Popula parâmetros das modalidades existentes
    modalidades = Modalidade.objects.exclude(nome__icontains='atletismo')
    for mod in modalidades:
        ParametroModalidade.objects.get_or_create(
            configuracao=config,
            modalidade=mod,
            defaults={'duracao_minutos': 50, 'intervalo_pos_jogo_minutos': 10}
        )

    # Popula fases padrão se nenhuma restrição foi cadastrada ainda
    if not config.restricoes_fases.exists():
        for f_cod, f_ordem in FASE_ORDEM_PADRAO.items():
            f_nome = FASE_NOMES_PADRAO.get(f_cod, f_cod)
            RestricaoFase.objects.get_or_create(
                configuracao=config,
                fase_codigo=f_cod,
                modalidade=None,
                defaults={
                    'fase_nome': f_nome,
                    'ordem_precedencia': f_ordem
                }
            )

    return config


def extrair_dados_para_motor(
    configuracao: ConfiguracaoGeral,
    modalidades_ids: Optional[List[int]] = None
) -> Tuple[List[DayWindow], List[ResourceConfig], List[PhaseConstraint], List[MatchRequest]]:
    """
    Extrai as entidades do banco de dados e as converte para as estruturas DTO desacopladas do motor.
    """
    # 1. Datas
    datas_qs = configuracao.datas.filter(ativo=True).order_by('data')
    days = [
        DayWindow(date=d.data, start_time=d.horario_inicio, end_time=d.horario_fim)
        for d in datas_qs
    ]

    # 2. Recursos
    recursos_qs = configuracao.recursos.filter(ativo=True).prefetch_related('modalidades_permitidas').order_by('ordem', 'nome')
    resources = []
    for r in recursos_qs:
        mod_ids = set(r.modalidades_permitidas.values_list('id', flat=True))
        resources.append(ResourceConfig(
            id=r.id,
            name=r.nome,
            allowed_modalities=mod_ids,
            order=r.ordem,
            is_active=r.ativo
        ))

    # 3. Restrições de Fases
    restricoes_qs = configuracao.restricoes_fases.prefetch_related('datas_permitidas').all()
    phase_constraints = []
    for rf in restricoes_qs:
        dates_set = {d.data for d in rf.datas_permitidas.filter(ativo=True)}
        phase_constraints.append(PhaseConstraint(
            phase_code=rf.fase_codigo,
            phase_name=rf.fase_nome or FASE_NOMES_PADRAO.get(rf.fase_codigo, rf.fase_codigo),
            modality_id=rf.modalidade_id,
            allowed_dates=dates_set,
            precedence_order=rf.ordem_precedencia
        ))

    # 4. Parâmetros de tempo por modalidade
    params_map = {
        p.modalidade_id: (p.duracao_minutos, p.intervalo_pos_jogo_minutos)
        for p in configuracao.parametros_modalidades.all()
    }

    # 5. Partidas do Chaveamento (Apenas jogos em Diamantina, excluindo eliminatórias de campi externos)
    partidas_qs = PartidaChaveamento.objects.filter(finalizada=False).exclude(
        chaveamento__modalidade__nome__icontains='atletismo'
    ).exclude(
        fase='EXTERNO_ELIMINATORIA'
    ).select_related(
        'chaveamento__modalidade', 'time_a', 'time_b', 'jogo', 'proxima_partida', 'partida_perdedor_destino'
    ).order_by('id')

    if modalidades_ids:
        partidas_qs = partidas_qs.filter(chaveamento__modalidade_id__in=modalidades_ids)

    # Identificação de dependências entre partidas
    # Se partida A define o participante da partida B, B depende de A.
    depends_on_map: Dict[int, List[int]] = {}
    for p in partidas_qs:
        if p.proxima_partida_id:
            depends_on_map.setdefault(p.proxima_partida_id, []).append(p.id)
        if p.partida_perdedor_destino_id:
            depends_on_map.setdefault(p.partida_perdedor_destino_id, []).append(p.id)

    matches: List[MatchRequest] = []
    for p in partidas_qs:
        mod = p.modalidade
        mod_id = mod.id if mod else None
        mod_name = mod.nome if mod else "Geral"

        dur, buff = params_map.get(
            mod_id,
            (configuracao.duracao_padrao_jogo_minutos, configuracao.intervalo_padrao_minutos)
        )

        f_disp = p.get_fase_display() if hasattr(p, 'get_fase_display') else p.fase
        t_a_nome = (p.time_a.nome_delegacao or p.time_a.nome_completo or p.time_a.email) if p.time_a else "A definir"
        t_b_nome = (p.time_b.nome_delegacao or p.time_b.nome_completo or p.time_b.email) if p.time_b else "A definir"

        prec_order = FASE_ORDEM_PADRAO.get(p.fase, 5)

        matches.append(MatchRequest(
            id=p.id,
            jogo_id=p.jogo_id,
            modality_id=mod_id,
            modality_name=mod_name,
            phase_code=p.fase,
            phase_display=f_disp,
            time_a_id=p.time_a_id,
            time_a_name=t_a_nome,
            time_b_id=p.time_b_id,
            time_b_name=t_b_nome,
            duration_minutes=dur,
            buffer_minutes=buff,
            depends_on_match_ids=depends_on_map.get(p.id, []),
            precedence_order=prec_order
        ))

    return days, resources, phase_constraints, matches


def executar_agendamento(
    configuracao: Optional[ConfiguracaoGeral] = None,
    modalidades_ids: Optional[List[int]] = None,
    titulo: Optional[str] = None
) -> CenarioExecucao:
    """
    Executa a resolução de agendamento automático e armazena o cenário com as alocações geradas.
    """
    if not configuracao:
        configuracao = obter_ou_criar_configuracao()

    days, resources, phase_constraints, matches = extrair_dados_para_motor(
        configuracao, modalidades_ids
    )

    solver = ScheduleSolver(
        days=days,
        resources=resources,
        phase_constraints=phase_constraints,
        matches=matches,
        min_team_rest_minutes=configuracao.descanso_minimo_equipe_minutos,
        default_buffer_minutes=configuracao.intervalo_padrao_minutos,
        max_daily_matches_per_team=configuracao.max_jogos_diarios_por_equipe,
        group_net_sports=configuracao.agrupar_modalidades_rede,
        net_sport_shift=getattr(configuracao, 'turno_bloco_rede', 'auto')
    )

    result = solver.solve()

    with transaction.atomic():
        cenario = CenarioExecucao.objects.create(
            configuracao=configuracao,
            titulo=titulo or f"Simulação de Cronograma ({timezone.localtime().strftime('%d/%m/%Y %H:%M')})",
            status='sucesso' if result.success else 'inviavel',
            mensagem_diagnostico=DiagnosticsFormatter.format_summary_text(result.issues),
            metricas=result.metrics
        )

        if result.success:
            itens = []
            recurso_obj_map = {r.id: r for r in configuracao.recursos.all()}
            for alloc in result.allocations:
                mr = alloc.match_request
                recurso_db = recurso_obj_map.get(alloc.resource_id)

                itens.append(ItemAlocacao(
                    cenario=cenario,
                    partida_chaveamento_id=mr.id if PartidaChaveamento.objects.filter(id=mr.id).exists() else None,
                    jogo_id=mr.jogo_id,
                    modalidade_nome=mr.modality_name,
                    fase_codigo=mr.phase_code,
                    fase_display=mr.phase_display,
                    time_a_id=mr.time_a_id,
                    time_a_nome=mr.time_a_name,
                    time_b_id=mr.time_b_id,
                    time_b_nome=mr.time_b_name,
                    data_alocada=alloc.date,
                    horario_inicio=alloc.start_time,
                    horario_fim=alloc.end_time,
                    recurso_local=recurso_db,
                    recurso_nome=alloc.resource_name,
                    status='alocado'
                ))
            ItemAlocacao.objects.bulk_create(itens)

    return cenario


def aplicar_cenario_ao_oficial(cenario: CenarioExecucao) -> Tuple[int, List[str]]:
    """
    Grava as datas, horários e quadras/locais de um cenário aprovado nas partidas reais
    (PartidaChaveamento e Jogo) do sistema.
    """
    if cenario.status == 'inviavel':
        raise ValueError("Não é possível aplicar um cenário inviável ou com conflitos.")

    atualizados = 0
    mensagens = []

    with transaction.atomic():
        for item in cenario.alocacoes.select_related('partida_chaveamento', 'jogo', 'recurso_local'):
            partida = item.partida_chaveamento
            if partida:
                partida.data_partida = item.data_alocada
                partida.horario_partida = item.horario_inicio
                partida.save()

                if partida.jogo:
                    partida.jogo.data_jogo = item.data_alocada
                    partida.jogo.horario_jogo = item.horario_inicio
                    partida.jogo.local = item.recurso_nome
                    partida.jogo.save()
                elif partida.time_a and partida.time_b and partida.time_a != partida.time_b:
                    mod = getattr(partida.chaveamento, 'modalidade', None)
                    if mod:
                        novo_jogo = Jogo.objects.create(
                            modalidade=mod,
                            data_jogo=item.data_alocada,
                            horario_jogo=item.horario_inicio,
                            time_a=partida.time_a,
                            time_b=partida.time_b,
                            local=item.recurso_nome
                        )
                        partida.jogo = novo_jogo
                        partida.save()
                atualizados += 1

            elif item.jogo:
                item.jogo.data_jogo = item.data_alocada
                item.jogo.horario_jogo = item.horario_inicio
                item.jogo.local = item.recurso_nome
                item.jogo.save()
                atualizados += 1

        cenario.status = 'aplicado'
        cenario.save()

    mensagens.append(f"{atualizados} partida(s) foram atualizadas no calendário oficial com sucesso!")
    return atualizados, mensagens


def resetar_todos_horarios(configuracao: Optional[ConfiguracaoGeral] = None) -> int:
    """
    Remove as datas, horários e quadras/locais de todas as partidas não finalizadas em Diamantina,
    permitindo redefinir e reexecutar a grade de agendamento do zero com segurança.
    """
    count = 0
    with transaction.atomic():
        partidas_qs = PartidaChaveamento.objects.filter(
            finalizada=False
        ).exclude(
            fase='EXTERNO_ELIMINATORIA'
        ).select_related('jogo')
        for p in partidas_qs:
            teve_alteracao = False
            if p.data_partida is not None or p.horario_partida is not None:
                p.data_partida = None
                p.horario_partida = None
                p.save()
                teve_alteracao = True

            if p.jogo and not p.jogo.finalizado:
                p.jogo.horario_jogo = None
                p.jogo.local = None
                p.jogo.save()
                teve_alteracao = True

            if teve_alteracao:
                count += 1

        # Atualiza status dos cenários aplicados para 'sucesso' (não aplicados)
        if configuracao:
            configuracao.cenarios.filter(status='aplicado').update(status='sucesso')
        else:
            CenarioExecucao.objects.filter(status='aplicado').update(status='sucesso')

    return count
