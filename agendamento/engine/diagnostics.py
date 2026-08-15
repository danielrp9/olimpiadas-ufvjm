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
                reasons_text.append("conflito de horário da mesma equipe")
            if reason_summary.get("team_rest", 0) > 0:
                reasons_text.append("intervalo de descanso obrigatório entre partidas da mesma equipe")
            if reason_summary.get("precedence", 0) > 0:
                reasons_text.append("jogos classificatórios anteriores necessários ainda não concluídos a tempo")
            if reason_summary.get("max_daily_matches", 0) > 0:
                reasons_text.append("limite de partidas diárias por equipe atingido para evitar desgaste")
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
        else:
            return DiagnosticIssue(
                code="MATCH_NO_VALID_SLOT",
                level="ERROR",
                phase_code=match.phase_code,
                phase_name=phase_name,
                message=f"Não foi possível encontrar um horário compatível para a partida '{match.modality_name}: {match.time_a_name} x {match.time_b_name}' ({phase_name}).",
                details=(
                    "Todas as datas gerais disponíveis foram avaliadas, porém houve esgotamento dos recursos, "
                    "conflitos de descanso de equipe ou incompatibilidade de precedência."
                ),
                recommendation="Revise a quantidade de quadras/recursos disponíveis ou adicione mais datas ao calendário geral da competição."
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
