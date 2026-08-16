from datetime import date
from typing import List, Dict, Optional, Any
from .models import DiagnosticIssue, MatchRequest, PhaseConstraint


class DiagnosticsFormatter:
    """
    Formatador e construtor de diagnósticos explicativos para o usuário.
    """

    @staticmethod
    def format_unallocated_match_issue(
        match: MatchRequest,
        phase_constraint: Optional[PhaseConstraint],
        attempted_dates: List[date],
        reason_summary: Dict[str, int]
    ) -> DiagnosticIssue:
        phase_name = match.phase_display or (phase_constraint.phase_name if phase_constraint else match.phase_code) or "Fase Desconhecida"

        if phase_constraint and phase_constraint.allowed_dates:
            dates_str = ", ".join(d.strftime('%d/%m/%Y') for d in phase_constraint.allowed_dates)
            
            # Razões mais comuns
            reasons_text = []
            if reason_summary.get("resource_busy", 0) > 0:
                reasons_text.append("conflito/ocupação dos recursos e quadras disponíveis")
            if reason_summary.get("team_conflict", 0) > 0:
                reasons_text.append("conflito de horário da mesma equipe na mesma modalidade")
            if reason_summary.get("team_rest", 0) > 0:
                reasons_text.append("intervalo de descanso obrigatório entre partidas da mesma equipe na modalidade")
            if reason_summary.get("precedence", 0) > 0:
                reasons_text.append("jogos classificatórios anteriores necessários ainda não concluídos a tempo")
            if reason_summary.get("max_daily_matches", 0) > 0:
                reasons_text.append("limite de partidas diárias por equipe na modalidade atingido")
            if reason_summary.get("net_sport_grouping", 0) > 0:
                reasons_text.append("regra de bloco contínuo para modalidades de rede (vôlei) na mesma quadra")
            if reason_summary.get("time_window", 0) > 0:
                reasons_text.append("limite de horário de funcionamento do dia excedido")

            details_reasons = (
                f" Principais fatores detectados durante as tentativas de alocação: {', '.join(reasons_text)}."
                if reasons_text else ""
            )

            return DiagnosticIssue(
                code="PHASE_CAPACITY_INSUFFICIENT",
                level="ERROR",
                phase_code=match.phase_code,
                phase_name=phase_name,
                message=f"Não foi possível alocar todas as partidas da fase '{phase_name}' na(s) data(s) definida(s).",
                details=(
                    f"A(s) data(s) permitida(s) ({dates_str}) não possui(em) capacidade ou horários compatíveis suficientes "
                    f"para acomodar a partida '{match.modality_name}: {match.time_a_name} x {match.time_b_name}' respeitando todas as regras configuradas."
                    f"{details_reasons}"
                ),
                recommendation="Selecione uma data adicional para esta fase, cadastre novos locais de jogo compatíveis ou amplie o horário limite de encerramento das datas."
            )
    @staticmethod
    def format_global_deficit_issue(
        all_matches: List[MatchRequest],
        unallocated_matches: List[MatchRequest],
        days: List[Any],
        resources: List[Any],
        reason_summary: Dict[str, int]
    ) -> DiagnosticIssue:
        total_matches_count = len(all_matches)
        unallocated_count = len(unallocated_matches)
        
        unallocated_demand_minutes = sum(m.total_slot_minutes for m in unallocated_matches)
        total_demand_minutes = sum(m.total_slot_minutes for m in all_matches)
        
        active_resources = [r for r in resources if getattr(r, 'is_active', True)]
        num_resources = max(1, len(active_resources))
        num_days = max(1, len(days))
        
        total_supply_minutes = sum(getattr(d, 'total_minutes', 720) for d in days) * num_resources
        
        unallocated_hours = unallocated_demand_minutes / 60
        total_demand_hours = total_demand_minutes / 60
        total_supply_hours = total_supply_minutes / 60
        
        # Agrupamento por modalidade e fase
        by_mod_phase: Dict[str, int] = {}
        for m in unallocated_matches:
            key = f"{m.modality_name} ({m.phase_display or m.phase_code})"
            by_mod_phase[key] = by_mod_phase.get(key, 0) + 1
        
        items_list = "\n".join(f"   • {mod_phase}: {count} jogo(s)" for mod_phase, count in by_mod_phase.items())
        
        # Cálculo de sugestões acionáveis
        avg_day_minutes = (sum(getattr(d, 'total_minutes', 720) for d in days) // num_days) if num_days > 0 else 720
        extra_days = max(1, -(-unallocated_demand_minutes // (avg_day_minutes * num_resources)))
        extra_courts = max(1, -(-unallocated_demand_minutes // max(1, sum(getattr(d, 'total_minutes', 720) for d in days))))
        extra_hours_per_day = round((unallocated_demand_minutes / (num_days * num_resources)) / 60, 1)

        # Fatores detectados
        reasons_text = []
        if reason_summary.get("resource_busy", 0) > 0:
            reasons_text.append("esgotamento dos horários das quadras")
        if reason_summary.get("team_conflict", 0) > 0:
            reasons_text.append("conflito de horários da mesma equipe na mesma modalidade")
        if reason_summary.get("team_rest", 0) > 0:
            reasons_text.append("tempo de descanso obrigatório entre jogos da mesma equipe na modalidade")
        if reason_summary.get("max_daily_matches", 0) > 0:
            reasons_text.append("limite de partidas diárias por equipe na modalidade atingido")
        if reason_summary.get("net_sport_grouping", 0) > 0:
            reasons_text.append("agrupamento em bloco contínuo de vôlei")
        if reason_summary.get("precedence", 0) > 0:
            reasons_text.append("precedência entre fases do chaveamento")

        details_reasons = f"Fatores restritivos detectados: {', '.join(reasons_text)}." if reasons_text else ""

        message = (
            f"{unallocated_count} partida(s) ficaram de fora do cronograma devido à falta de horários suficientes nas datas cadastradas."
        )

        details = (
            f"📊 Balanço de Horários e Capacidade:\n"
            f"• Demanda total dos jogos: {total_demand_hours:.1f}h ({total_demand_minutes} min para {total_matches_count} partidas)\n"
            f"• Capacidade ofertada: {total_supply_hours:.1f}h ({total_supply_minutes} min em {num_resources} quadra(s) ao longo de {num_days} dia(s))\n"
            f"• Déficit de tempo: Faltam aproximadamente {unallocated_count} horários de jogos (cerca de {unallocated_hours:.1f} horas de tempo em quadra).\n\n"
            f"Jogos que não puderam ser alocados:\n{items_list}\n\n"
            f"{details_reasons}"
        )

        recommendation = (
            f"Para comportar todas as partidas sem conflitos, você pode:\n"
            f"1. Adicionar +{extra_days} data(s) ao calendário geral da competição;\n"
            f"2. Cadastrar +{extra_courts} quadra(s) compatível(is) no menu de Recursos e Locais; ou\n"
            f"3. Ampliar o horário de funcionamento das quadras em aprox. +{extra_hours_per_day}h por dia."
        )

        return DiagnosticIssue(
            code="GLOBAL_SCHEDULE_DEFICIT",
            level="ERROR",
            message=message,
            details=details,
            recommendation=recommendation
        )

    @staticmethod
    def format_summary_text(issues: List[DiagnosticIssue]) -> str:
        if not issues:
            return "Cronograma gerado com sucesso sem pendências."

        lines = []
        errors = [i for i in issues if i.level == 'ERROR']
        warnings = [i for i in issues if i.level == 'WARNING']

        if errors:
            lines.append(f"❌ Foram encontrados {len(errors)} impedimento(s) que inviabilizam o cronograma:")
            for idx, err in enumerate(errors, 1):
                lines.append(f"\n{idx}. {err.message}")
                if err.details:
                    lines.append(f"   • Detalhe: {err.details}")
                if err.recommendation:
                    lines.append(f"   • O que fazer: {err.recommendation}")

        if warnings:
            lines.append(f"\n⚠️ Avisos ({len(warnings)}):")
            for idx, w in enumerate(warnings, 1):
                lines.append(f"   {idx}. {w.message}")

        return "\n".join(lines)
