from datetime import date, time
from django.test import TestCase
from agendamento.engine import (
    DayWindow, ResourceConfig, PhaseConstraint, MatchRequest,
    ScheduleSolver, ScheduleValidator
)


class PhaseRestrictionsDocumentTests(TestCase):
    """
    Testes específicos para todas as cláusulas do documento 'regras_automatizacao_horario.txt'.
    """

    def setUp(self):
        # Calendário de teste
        self.d_04_09 = DayWindow(date=date(2026, 9, 4), start_time=time(8, 0), end_time=time(20, 0))
        self.d_19_09 = DayWindow(date=date(2026, 9, 19), start_time=time(8, 0), end_time=time(20, 0))
        self.d_20_09 = DayWindow(date=date(2026, 9, 20), start_time=time(8, 0), end_time=time(20, 0))
        self.d_25_09 = DayWindow(date=date(2026, 9, 25), start_time=time(8, 0), end_time=time(20, 0))
        self.d_26_09 = DayWindow(date=date(2026, 9, 26), start_time=time(8, 0), end_time=time(20, 0))
        self.d_27_09 = DayWindow(date=date(2026, 9, 27), start_time=time(8, 0), end_time=time(20, 0))
        
        self.all_days = [
            self.d_04_09, self.d_19_09, self.d_20_09,
            self.d_25_09, self.d_26_09, self.d_27_09
        ]
        self.quadra_principal = ResourceConfig(id=1, name="Quadra Principal", is_active=True)

    def test_regra_3_e_11_semifinal_nunca_antecipada(self):
        """
        Documento Seção 3 e 11:
        Semifinal configurada para 26/09.
        Mesmo existindo espaço disponível em 19/09, 20/09 e 25/09,
        a semifinal NÃO PODE ser agendada nesses dias e deve permanecer em 26/09.
        """
        phase_constraints = [
            PhaseConstraint(phase_code="SEMIFINAL", phase_name="Semifinal", allowed_dates={date(2026, 9, 26)}),
            PhaseConstraint(phase_code="FINAL", phase_name="Final", allowed_dates={date(2026, 9, 27)}),
        ]
        matches = [
            MatchRequest(id=1, modality_id=1, modality_name="Futsal", phase_code="CLASSIFICATORIA", phase_display="Fase Classificatória", time_a_id=1, time_b_id=2, duration_minutes=60, buffer_minutes=10, precedence_order=1),
            MatchRequest(id=2, modality_id=1, modality_name="Futsal", phase_code="SEMIFINAL", phase_display="Semifinal", time_a_id=3, time_b_id=4, duration_minutes=60, buffer_minutes=10, precedence_order=2),
            MatchRequest(id=3, modality_id=1, modality_name="Futsal", phase_code="FINAL", phase_display="Final", time_a_id=5, time_b_id=6, duration_minutes=60, buffer_minutes=10, precedence_order=3),
        ]

        solver = ScheduleSolver(
            days=self.all_days,
            resources=[self.quadra_principal],
            phase_constraints=phase_constraints,
            matches=matches
        )
        result = solver.solve()
        self.assertTrue(result.success)

        alloc_map = {a.match_id: a for a in result.allocations}
        self.assertEqual(alloc_map[2].date, date(2026, 9, 26), "Semifinal deve ser alocada estritamente em 26/09")
        self.assertEqual(alloc_map[3].date, date(2026, 9, 27), "Final deve ser alocada estritamente em 27/09")

    def test_regra_4_fases_sem_restricao_especifica(self):
        """
        Documento Seção 4:
        Se uma fase não possuir uma data específica configurada, ela poderá utilizar qualquer data geral compatível.
        """
        # Fase classificatória sem restrição de data
        matches = [
            MatchRequest(id=1, modality_id=1, modality_name="Futsal", phase_code="CLASSIFICATORIA", time_a_id=1, time_b_id=2, duration_minutes=60, buffer_minutes=10),
        ]
        solver = ScheduleSolver(
            days=self.all_days,
            resources=[self.quadra_principal],
            phase_constraints=[],
            matches=matches
        )
        result = solver.solve()
        self.assertTrue(result.success)
        self.assertIn(result.allocations[0].date, [d.date for d in self.all_days])

    def test_regra_6_incompatibilidade_de_ordem_precedencia(self):
        """
        Documento Seção 6:
        Exemplo inválido: Semifinal -> 27/09 e Final -> 26/09.
        O sistema deve detectar e informar que as datas das fases são incompatíveis com a ordem do chaveamento.
        """
        phase_constraints = [
            PhaseConstraint(phase_code="SEMIFINAL", phase_name="Semifinal", allowed_dates={date(2026, 9, 27)}),
            PhaseConstraint(phase_code="FINAL", phase_name="Final", allowed_dates={date(2026, 9, 26)}),
        ]
        matches = [
            MatchRequest(id=1, modality_id=1, modality_name="Futsal", phase_code="SEMIFINAL", phase_display="Semifinal", precedence_order=1),
            MatchRequest(id=2, modality_id=1, modality_name="Futsal", phase_code="FINAL", phase_display="Final", depends_on_match_ids=[1], precedence_order=2),
        ]

        issues = ScheduleValidator.validate_inputs(
            days=self.all_days,
            resources=[self.quadra_principal],
            phase_constraints=phase_constraints,
            matches=matches
        )
        
        error_codes = [i.code for i in issues if i.level == 'ERROR']
        self.assertIn("INCOMPATIBLE_PHASE_PRECEDENCE", error_codes)

    def test_regra_8_e_10_capacidade_insuficiente_em_fase_restrita(self):
        """
        Documento Seção 8 e 10:
        Se uma data permitida para a fase não tiver capacidade para todos os jogos daquela fase,
        o sistema NÃO deve mover automaticamente para outra data não permitida.
        Deve falhar e emitir diagnóstico claro de capacidade insuficiente.
        """
        # Janela de apenas 2 horas em 26/09 (08:00 às 10:00) = 120 minutos
        dia_curto = DayWindow(date=date(2026, 9, 26), start_time=time(8, 0), end_time=time(10, 0))
        
        # 4 jogos de semifinal com 60 minutos cada = 240 minutos de demanda
        phase_constraints = [
            PhaseConstraint(phase_code="SEMIFINAL", phase_name="Semifinal", allowed_dates={date(2026, 9, 26)}),
        ]
        matches = [
            MatchRequest(id=1, modality_id=1, modality_name="Futsal", phase_code="SEMIFINAL", phase_display="Semifinal", duration_minutes=50, buffer_minutes=10),
            MatchRequest(id=2, modality_id=1, modality_name="Futsal", phase_code="SEMIFINAL", phase_display="Semifinal", duration_minutes=50, buffer_minutes=10),
            MatchRequest(id=3, modality_id=1, modality_name="Futsal", phase_code="SEMIFINAL", phase_display="Semifinal", duration_minutes=50, buffer_minutes=10),
            MatchRequest(id=4, modality_id=1, modality_name="Futsal", phase_code="SEMIFINAL", phase_display="Semifinal", duration_minutes=50, buffer_minutes=10),
        ]

        solver = ScheduleSolver(
            days=[dia_curto, self.d_04_09, self.d_19_09],  # Outros dias disponíveis com muito espaço
            resources=[self.quadra_principal],
            phase_constraints=phase_constraints,
            matches=matches
        )
        result = solver.solve()
        self.assertFalse(result.success, "Não deve ter sucesso pois não cabem os 4 jogos em 26/09 e não pode transbordar")
        
        # Verifica se os diagnósticos contêm explicação de capacidade
        error_msgs = " ".join(i.message for i in result.issues)
        self.assertTrue(
            "Não foi possível" in error_msgs or "capacidade" in error_msgs or "insuficiente" in error_msgs.lower()
        )

    def test_regra_12_configuracao_generica_para_qualquer_fase(self):
        """
        Documento Seção 12:
        Garante que o mecanismo funciona para qualquer código de fase arbitrário (ex: OITAVAS, REPESCAGEM, DISPUTA_5_LUGAR).
        """
        phase_constraints = [
            PhaseConstraint(phase_code="DISPUTA_5_LUGAR", phase_name="Disputa 5º Lugar", allowed_dates={date(2026, 9, 25)}),
        ]
        matches = [
            MatchRequest(id=100, modality_id=1, modality_name="Peteca", phase_code="DISPUTA_5_LUGAR", phase_display="Disputa 5º Lugar", time_a_id=1, time_b_id=2),
        ]
        solver = ScheduleSolver(
            days=self.all_days,
            resources=[self.quadra_principal],
            phase_constraints=phase_constraints,
            matches=matches
        )
        result = solver.solve()
        self.assertTrue(result.success)
        self.assertEqual(result.allocations[0].date, date(2026, 9, 25))
