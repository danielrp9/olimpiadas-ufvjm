from datetime import date, time, datetime, timedelta
from typing import List, Dict, Set, Optional, Tuple, Any
import copy

from .models import (
    DayWindow, ResourceConfig, PhaseConstraint, MatchRequest,
    AllocatedSlot, DiagnosticIssue, EngineResult
)
from .validator import ScheduleValidator
from .diagnostics import DiagnosticsFormatter


class ScheduleSolver:
    """
    Motor inteligente de alocação de jogos e geração de cronograma.
    Respeita restrições rígidas de datas por fase, disponibilidade de quadras/recursos,
    conflitos e descansos de equipes, precedência de chaveamento e janelas de horário.
    """

    def __init__(
        self,
        days: List[DayWindow],
        resources: List[ResourceConfig],
        phase_constraints: List[PhaseConstraint],
        matches: List[MatchRequest],
        min_team_rest_minutes: int = 60,
        default_buffer_minutes: int = 10,
        max_daily_matches_per_team: int = 2,
        group_net_sports: bool = True,
        time_slot_step_minutes: int = 15,
        max_backtrack_nodes: int = 50000
    ):
        self.days = sorted(days, key=lambda d: d.date)
        self.resources = sorted(resources, key=lambda r: (r.order, r.name))
        self.phase_constraints = {pc.phase_code: pc for pc in phase_constraints}
        self.matches = matches
        self.min_team_rest_minutes = min_team_rest_minutes
        self.default_buffer_minutes = default_buffer_minutes
        self.max_daily_matches_per_team = max_daily_matches_per_team
        self.group_net_sports = group_net_sports
        self.time_slot_step_minutes = max(5, time_slot_step_minutes)
        self.max_backtrack_nodes = max_backtrack_nodes

    def solve(self) -> EngineResult:
        # 1. Validação Preliminar
        pre_issues = ScheduleValidator.validate_inputs(
            self.days, self.resources, list(self.phase_constraints.values()), self.matches
        )
        critical_errors = [i for i in pre_issues if i.level == 'ERROR']
        if critical_errors:
            return EngineResult(
                success=False,
                allocations=[],
                issues=pre_issues,
                metrics={'error_type': 'PRE_VALIDATION_FAILED'}
            )

        if not self.matches:
            return EngineResult(
                success=True,
                allocations=[],
                issues=[DiagnosticIssue(
                    code="NO_MATCHES",
                    level="INFO",
                    message="Nenhuma partida pendente de agendamento."
                )],
                metrics={'total_matches': 0}
            )

        # 2. Ordenação das variáveis (Partidas)
        sorted_matches = self._order_matches(self.matches)

        # 3. Execução da Busca com Backtracking Otimizado
        allocations: List[AllocatedSlot] = []
        failure_diagnostic_data: Dict[Any, Dict[str, Any]] = {}
        nodes_count = [0]

        # Índices de estado para verificação O(1) de conflitos
        alloc_map: Dict[Any, AllocatedSlot] = {}
        allocs_by_res_date: Dict[Tuple[Any, date], List[AllocatedSlot]] = {}
        allocs_by_team_date: Dict[Tuple[Any, date], List[AllocatedSlot]] = {}

        success = self._backtrack(
            index=0,
            matches=sorted_matches,
            current_allocations=allocations,
            alloc_map=alloc_map,
            allocs_by_res_date=allocs_by_res_date,
            allocs_by_team_date=allocs_by_team_date,
            failure_data=failure_diagnostic_data,
            nodes_count=nodes_count
        )

        if success:
            metrics = self._calculate_metrics(allocations)
            return EngineResult(
                success=True,
                allocations=allocations,
                issues=pre_issues,  # Warnings se houver
                metrics=metrics
            )
        else:
            # 4. Formatação de Diagnóstico Explicativo em caso de Inviabilidade
            issues = list(pre_issues)
            unallocated_match = None
            for m in sorted_matches:
                if not any(a.match_id == m.id for a in allocations):
                    unallocated_match = m
                    break

            if unallocated_match:
                pc = self.phase_constraints.get(unallocated_match.phase_code)
                diag_info = failure_diagnostic_data.get(unallocated_match.id, {})
                reasons = diag_info.get('reasons', {})
                attempted_dates = diag_info.get('attempted_dates', [])
                
                issue = DiagnosticsFormatter.format_unallocated_match_issue(
                    match=unallocated_match,
                    phase_constraint=pc,
                    attempted_dates=attempted_dates,
                    reason_summary=reasons
                )
                issues.append(issue)

            return EngineResult(
                success=False,
                allocations=[],
                issues=issues,
                metrics={'nodes_explored': nodes_count[0]}
            )

    def _order_matches(self, matches: List[MatchRequest]) -> List[MatchRequest]:
        """
        Ordena as partidas considerando precedência topológica, restrições rígidas de datas (MRV)
        e ordem natural das fases do torneio.
        """
        # 1. Mapeamento de dependências
        match_by_id = {m.id: m for m in matches}
        in_degree: Dict[Any, int] = {m.id: len(m.depends_on_match_ids) for m in matches}
        dependents: Dict[Any, List[Any]] = {m.id: [] for m in matches}
        for m in matches:
            for dep_id in m.depends_on_match_ids:
                if dep_id in dependents:
                    dependents[dep_id].append(m.id)

        # 2. Heurística de Domínio (quantas datas permitidas a partida tem)
        def domain_size(m: MatchRequest) -> int:
            pc = self.phase_constraints.get(m.phase_code)
            if pc and pc.allowed_dates:
                return len(pc.allowed_dates)
            return len(self.days) + 10  # Não restringido = domínio maior

        # 3. Topological sorting com desempate por restrição de data, agrupamento de rede e precedência
        ready = [m for m in matches if in_degree[m.id] == 0]
        sorted_list: List[MatchRequest] = []

        while ready:
            # Seleciona o elemento mais restrito (menor domínio de datas, menor precedencia_order, agrupando rede)
            ready.sort(key=lambda m: (m.precedence_order, 0 if m.is_net_sport else 1, domain_size(m), m.modality_id or 0, m.id))
            current = ready.pop(0)
            sorted_list.append(current)

            for nxt_id in dependents.get(current.id, []):
                in_degree[nxt_id] -= 1
                if in_degree[nxt_id] == 0:
                    ready.append(match_by_id[nxt_id])

        # Caso haja ciclos ou partidas restantes não alcançadas
        if len(sorted_list) < len(matches):
            remaining = [m for m in matches if m not in sorted_list]
            remaining.sort(key=lambda m: (m.precedence_order, 0 if m.is_net_sport else 1, domain_size(m), m.modality_id or 0, m.id))
            sorted_list.extend(remaining)

        return sorted_list

    def _backtrack(
        self,
        index: int,
        matches: List[MatchRequest],
        current_allocations: List[AllocatedSlot],
        alloc_map: Dict[Any, AllocatedSlot],
        allocs_by_res_date: Dict[Tuple[Any, date], List[AllocatedSlot]],
        allocs_by_team_date: Dict[Tuple[Any, date], List[AllocatedSlot]],
        failure_data: Dict[Any, Dict[str, Any]],
        nodes_count: List[int]
    ) -> bool:
        if index >= len(matches):
            return True

        nodes_count[0] += 1
        if nodes_count[0] > self.max_backtrack_nodes:
            return False

        match = matches[index]
        pc = self.phase_constraints.get(match.phase_code)

        # Determina datas candidatas
        candidate_days: List[DayWindow] = []
        if pc and pc.allowed_dates:
            # Restrição rígida de data da fase!
            for d in self.days:
                if d.date in pc.allowed_dates:
                    candidate_days.append(d)
        else:
            # Qualquer data geral disponível
            candidate_days = list(self.days)

        if not candidate_days:
            failure_data[match.id] = {
                'reasons': {'no_allowed_dates': 1},
                'attempted_dates': []
            }
            return False

        reasons_counter = {
            'resource_busy': 0,
            'team_conflict': 0,
            'team_rest': 0,
            'max_daily_matches': 0,
            'net_sport_grouping': 0,
            'precedence': 0,
            'time_window': 0
        }
        attempted_dates = [d.date for d in candidate_days]

        # Recursos compatíveis
        compatible_resources = [
            r for r in self.resources
            if r.is_active and r.accepts_modality(match.modality_id)
        ]

        # Gera combinações de slots válidos
        for day in candidate_days:
            # Verifica precedência temporal com partidas antecessoras já alocadas
            min_start_datetime = self._get_min_start_from_dependencies(match, alloc_map)
            if min_start_datetime and min_start_datetime.date() > day.date:
                reasons_counter['precedence'] += 1
                continue

            day_start_dt = datetime.combine(day.date, day.start_time)
            day_end_dt = datetime.combine(day.date, day.end_time)
            match_duration = timedelta(minutes=match.duration_minutes)
            buffer_duration = timedelta(minutes=match.buffer_minutes)
            slot_step = timedelta(minutes=self.time_slot_step_minutes)

            # Itera sobre os horários possíveis do dia
            current_time_dt = day_start_dt
            if min_start_datetime and min_start_datetime.date() == day.date:
                if min_start_datetime > current_time_dt:
                    current_time_dt = min_start_datetime

            while current_time_dt + match_duration <= day_end_dt:
                slot_start_dt = current_time_dt
                slot_end_dt = current_time_dt + match_duration

                for resource in compatible_resources:
                    # Checagem de conflitos ultra-rápida via índices
                    is_valid, reason = self._is_slot_valid(
                        match=match,
                        slot_start=slot_start_dt,
                        slot_end=slot_end_dt,
                        resource=resource,
                        buffer_duration=buffer_duration,
                        allocs_by_res_date=allocs_by_res_date,
                        allocs_by_team_date=allocs_by_team_date
                    )

                    if not is_valid:
                        if reason in reasons_counter:
                            reasons_counter[reason] += 1
                        continue

                    # Aloca provisoriamente
                    allocated_slot = AllocatedSlot(
                        match_id=match.id,
                        match_request=match,
                        date=day.date,
                        start_time=slot_start_dt.time(),
                        end_time=slot_end_dt.time(),
                        resource_id=resource.id,
                        resource_name=resource.name
                    )
                    
                    # Atualiza estruturas de estado
                    current_allocations.append(allocated_slot)
                    alloc_map[match.id] = allocated_slot
                    allocs_by_res_date.setdefault((resource.id, day.date), []).append(allocated_slot)
                    for t in match.teams:
                        allocs_by_team_date.setdefault((t, day.date), []).append(allocated_slot)

                    # Passo recursivo
                    if self._backtrack(
                        index + 1, matches, current_allocations,
                        alloc_map, allocs_by_res_date, allocs_by_team_date,
                        failure_data, nodes_count
                    ):
                        return True

                    # Desfaz alocação
                    current_allocations.pop()
                    del alloc_map[match.id]
                    allocs_by_res_date[(resource.id, day.date)].pop()
                    for t in match.teams:
                        allocs_by_team_date[(t, day.date)].pop()

                current_time_dt += slot_step

        failure_data[match.id] = {
            'reasons': reasons_counter,
            'attempted_dates': attempted_dates
        }
        return False

    def _is_slot_valid(
        self,
        match: MatchRequest,
        slot_start: datetime,
        slot_end: datetime,
        resource: ResourceConfig,
        buffer_duration: timedelta,
        allocs_by_res_date: Dict[Tuple[Any, date], List[AllocatedSlot]],
        allocs_by_team_date: Dict[Tuple[Any, date], List[AllocatedSlot]]
    ) -> Tuple[bool, str]:
        """
        Verifica se o slot atende a todas as restrições com complexidade O(1)/O(k).
        """
        target_date = slot_start.date()
        rest_duration = timedelta(minutes=self.min_team_rest_minutes)
        match_teams = match.teams

        # 1. Limite de partidas por dia por equipe
        if self.max_daily_matches_per_team > 0:
            for t_id in match_teams:
                existing_team_matches = allocs_by_team_date.get((t_id, target_date), [])
                if len(existing_team_matches) >= self.max_daily_matches_per_team:
                    return False, 'max_daily_matches'

        # 2. Agrupamento em bloco contínuo de modalidades de rede (ex: Vôlei) na mesma quadra
        res_date_allocs = allocs_by_res_date.get((resource.id, target_date), [])
        if self.group_net_sports and res_date_allocs:
            timeline = [(a.start_time, a.match_request.is_net_sport) for a in res_date_allocs]
            timeline.append((slot_start.time(), match.is_net_sport))
            timeline.sort(key=lambda item: item[0])
            
            transitions = 0
            for i in range(1, len(timeline)):
                if timeline[i][1] != timeline[i-1][1]:
                    transitions += 1
            
            if transitions > 1:
                return False, 'net_sport_grouping'

        # 3. Conflito no mesmo Recurso (apenas jogos no mesmo recurso e mesma data)
        for alloc in res_date_allocs:
            alloc_start = alloc.start_datetime
            alloc_end = alloc.end_datetime
            alloc_buffer = timedelta(minutes=alloc.match_request.buffer_minutes)

            res_busy_start = alloc_start
            res_busy_end = alloc_end + alloc_buffer
            cand_busy_start = slot_start
            cand_busy_end = slot_end + buffer_duration

            if (cand_busy_start < res_busy_end) and (cand_busy_end > res_busy_start):
                return False, 'resource_busy'

        # 4. Conflito e descanso de Equipes (apenas jogos dos times na mesma data)
        for t_id in match_teams:
            team_allocs = allocs_by_team_date.get((t_id, target_date), [])
            for alloc in team_allocs:
                alloc_start = alloc.start_datetime
                alloc_end = alloc.end_datetime

                # Checagem de sobreposição exata
                if (slot_start < alloc_end) and (slot_end > alloc_start):
                    return False, 'team_conflict'

                # Intervalo de Descanso da Equipe
                if slot_start >= alloc_end and (slot_start - alloc_end) < rest_duration:
                    return False, 'team_rest'

                if alloc_start >= slot_end and (alloc_start - slot_end) < rest_duration:
                    return False, 'team_rest'

        return True, 'ok'

    def _get_min_start_from_dependencies(
        self,
        match: MatchRequest,
        alloc_map: Dict[Any, AllocatedSlot]
    ) -> Optional[datetime]:
        """
        Retorna o datetime mínimo em que a partida pode começar baseado
        nas partidas antecessoras que ela depende (lookup O(1)).
        """
        if not match.depends_on_match_ids:
            return None

        min_start = None
        rest_delta = timedelta(minutes=self.min_team_rest_minutes)

        for dep_id in match.depends_on_match_ids:
            parent_alloc = alloc_map.get(dep_id)
            if parent_alloc:
                earliest_possible = parent_alloc.end_datetime + rest_delta
                if min_start is None or earliest_possible > min_start:
                    min_start = earliest_possible

        return min_start

    def _calculate_metrics(self, allocations: List[AllocatedSlot]) -> Dict[str, Any]:
        """Calcula métricas de qualidade e utilização do cronograma gerado."""
        if not allocations:
            return {'total_matches': 0}

        dates_used = sorted(list({a.date for a in allocations}))
        resources_used = sorted(list({a.resource_name for a in allocations}))
        
        matches_by_date = {}
        for a in allocations:
            d_str = a.date.strftime('%Y-%m-%d')
            matches_by_date[d_str] = matches_by_date.get(d_str, 0) + 1

        matches_by_resource = {}
        for a in allocations:
            matches_by_resource[a.resource_name] = matches_by_resource.get(a.resource_name, 0) + 1

        return {
            'total_matches': len(allocations),
            'dates_used_count': len(dates_used),
            'dates_used': [d.strftime('%d/%m/%Y') for d in dates_used],
            'resources_used_count': len(resources_used),
            'resources_used': resources_used,
            'matches_by_date': matches_by_date,
            'matches_by_resource': matches_by_resource
        }
