from datetime import date, datetime
from typing import List, Dict, Set, Optional, Tuple, Any
from .models import (
    DayWindow, ResourceConfig, PhaseConstraint, MatchRequest, DiagnosticIssue
)


class PreValidationException(Exception):
    def __init__(self, issues: List[DiagnosticIssue]):
        self.issues = issues
        super().__init__("; ".join(i.message for i in issues))


class ScheduleValidator:
    """
    Validador de consistência preliminar e restrições estruturais
    antes da resolução do cronograma.
    """

    @staticmethod
    def validate_inputs(
        days: List[DayWindow],
        resources: List[ResourceConfig],
        phase_constraints: List[PhaseConstraint],
        matches: List[MatchRequest]
    ) -> List[DiagnosticIssue]:
        issues: List[DiagnosticIssue] = []

        # 1. Validação de Datas Gerais
        if not days:
            issues.append(DiagnosticIssue(
                code="NO_DAYS_CONFIGURED",
                level="ERROR",
                message="Nenhuma data de competição foi cadastrada ou ativada.",
                details="O gerador necessita de pelo menos uma data válida para alocar as partidas.",
                recommendation="Cadastre as datas gerais da competição no menu de Datas Disponíveis."
            ))
            return issues

        available_dates_set = {d.date for d in days}

        # 2. Validação de Recursos/Quadras
        active_resources = [r for r in resources if r.is_active]
        if not active_resources:
            issues.append(DiagnosticIssue(
                code="NO_RESOURCES_CONFIGURED",
                level="ERROR",
                message="Nenhum local ou recurso de jogo ativo foi encontrado.",
                details="O gerador precisa de quadras ou locais cadastrados para definir onde as partidas ocorrerão.",
                recommendation="Cadastre as quadras/locais no menu de Recursos e Locais."
            ))
            return issues

        # 3. Compatibilidade Modalidade x Recurso
        modalities_in_matches: Dict[Any, str] = {m.modality_id: m.modality_name for m in matches if m.modality_id}
        for mod_id, mod_name in modalities_in_matches.items():
            compatible_res = [r for r in active_resources if r.accepts_modality(mod_id)]
            if not compatible_res:
                issues.append(DiagnosticIssue(
                    code="MODALITY_NO_COMPATIBLE_RESOURCE",
                    level="ERROR",
                    message=f"A modalidade '{mod_name}' não possui nenhum local de jogo compatível.",
                    details=f"Existem partidas previstas para '{mod_name}', mas nenhuma quadra/local aceita esta modalidade.",
                    recommendation=f"Edite uma ou mais quadras/locais e marque a modalidade '{mod_name}' como permitida."
                ))

        # 4. Validação de Datas de Fases vs Datas Gerais
        phase_map: Dict[str, PhaseConstraint] = {pc.phase_code: pc for pc in phase_constraints}
        for pc in phase_constraints:
            if pc.allowed_dates:
                invalid_dates = pc.allowed_dates - available_dates_set
                if invalid_dates:
                    dates_str = ", ".join(d.strftime('%d/%m/%Y') for d in invalid_dates)
                    issues.append(DiagnosticIssue(
                        code="PHASE_DATE_NOT_IN_GENERAL_DATES",
                        level="ERROR",
                        phase_code=pc.phase_code,
                        phase_name=pc.phase_name,
                        message=f"A fase '{pc.phase_name or pc.phase_code}' possui datas permitidas que não constam nas datas gerais.",
                        details=f"Datas fora do calendário geral: {dates_str}.",
                        recommendation="Inclua essas datas no calendário geral da competição ou ajuste as datas permitidas da fase."
                    ))

        # 5. Validação de Precedência Lógica entre Fases Dependentes
        # Se uma partida B depende da partida A (A precede B):
        # As datas de A devem permitir que A termine antes de B.
        match_by_id = {m.id: m for m in matches}
        for match in matches:
            for dep_id in match.depends_on_match_ids:
                parent = match_by_id.get(dep_id)
                if not parent:
                    continue

                parent_phase_c = phase_map.get(parent.phase_code)
                child_phase_c = phase_map.get(match.phase_code)

                if parent_phase_c and child_phase_c:
                    if parent_phase_c.allowed_dates and child_phase_c.allowed_dates:
                        min_child_date = min(child_phase_c.allowed_dates)
                        max_parent_date = max(parent_phase_c.allowed_dates)
                        min_parent_date = min(parent_phase_c.allowed_dates)

                        # Se a data mínima do filho for menor que a data mínima do pai (ex: Semi 27/09 e Final 26/09)
                        if min_child_date < min_parent_date:
                            issues.append(DiagnosticIssue(
                                code="INCOMPATIBLE_PHASE_PRECEDENCE",
                                level="ERROR",
                                phase_code=match.phase_code,
                                phase_name=match.phase_display or match.phase_code,
                                message=f"Datas incompatíveis com a ordem do chaveamento entre '{parent.phase_display}' e '{match.phase_display}'.",
                                details=(
                                    f"A fase antecessora '{parent.phase_display}' está configurada para iniciar em "
                                    f"{min_parent_date.strftime('%d/%m/%Y')}, enquanto a fase seguinte '{match.phase_display}' "
                                    f"está configurada para {min_child_date.strftime('%d/%m/%Y')}."
                                ),
                                recommendation="Ajuste as datas permitidas para que a fase seguinte ocorra na mesma data (em horário posterior) ou em data posterior à fase anterior."
                            ))

        # 6. Verificação de Capacidade Teórica Máxima por Fase com Restrição Rígida
        # Se uma fase X tem N partidas e uma data específica D:
        # Verifica se o tempo total disponível em D nos recursos compatíveis suporta N partidas.
        day_map = {d.date: d for d in days}
        matches_by_phase: Dict[str, List[MatchRequest]] = {}
        for m in matches:
            matches_by_phase.setdefault(m.phase_code, []).append(m)

        for phase_code, p_matches in matches_by_phase.items():
            pc = phase_map.get(phase_code)
            if pc and pc.allowed_dates:
                # Calcula minutos necessários
                total_duration_req = sum(m.total_slot_minutes for m in p_matches)
                # Calcula minutos totais ofertados pelas datas permitidas nos recursos compatíveis
                total_duration_available = 0
                for allowed_d in pc.allowed_dates:
                    day_w = day_map.get(allowed_d)
                    if not day_w:
                        continue
                    for r in active_resources:
                        # Recurso aceita as modalidades das partidas?
                        for m in p_matches:
                            if r.accepts_modality(m.modality_id):
                                total_duration_available += day_w.total_minutes
                                break

                if total_duration_available < total_duration_req:
                    dates_str = ", ".join(d.strftime('%d/%m/%Y') for d in pc.allowed_dates)
                    p_name = pc.phase_name or phase_code
                    deficit_minutes = total_duration_req - total_duration_available
                    avg_slot = (total_duration_req // len(p_matches)) if p_matches else 50
                    deficit_games = max(1, -(-deficit_minutes // max(1, avg_slot)))
                    
                    req_hours = total_duration_req / 60
                    avail_hours = total_duration_available / 60
                    def_hours = deficit_minutes / 60

                    issues.append(DiagnosticIssue(
                        code="THEORETICAL_CAPACITY_INSUFFICIENT",
                        level="ERROR",
                        phase_code=phase_code,
                        phase_name=p_name,
                        message=f"Capacidade insuficiente: {deficit_games} partida(s) da fase '{p_name}' não puderam ser alocadas por falta de horários na(s) data(s) permitida(s).",
                        details=(
                            f"📊 Balanço da Fase '{p_name}':\n"
                            f"• Partidas na fase: {len(p_matches)} jogos ({req_hours:.1f}h / {total_duration_req} min de demanda)\n"
                            f"• Capacidade ofertada em {dates_str}: {avail_hours:.1f}h ({total_duration_available} min nas quadras compatíveis)\n"
                            f"• Déficit de horários: Faltam aproximadamente {deficit_games} horários de jogos (cerca de {def_hours:.1f} horas de tempo em quadra)."
                        ),
                        recommendation="Selecione uma data adicional para esta fase, adicione recursos/quadras compatíveis ou amplie a janela de horários de funcionamento."
                    ))

        return issues
