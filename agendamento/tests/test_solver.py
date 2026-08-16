from datetime import date, time, datetime
from django.test import TestCase
from agendamento.engine import (
    DayWindow, ResourceConfig, PhaseConstraint, MatchRequest,
    ScheduleSolver, ScheduleValidator
)


class ScheduleSolverEngineTests(TestCase):
    """
    Testes unitários detalhados do motor e algoritmo de agendamento (pure Python engine).
    """

    def setUp(self):
        self.d1 = DayWindow(date=date(2026, 9, 19), start_time=time(8, 0), end_time=time(18, 0))
        self.d2 = DayWindow(date=date(2026, 9, 20), start_time=time(8, 0), end_time=time(18, 0))
        self.d3 = DayWindow(date=date(2026, 9, 26), start_time=time(8, 0), end_time=time(18, 0))
        self.d4 = DayWindow(date=date(2026, 9, 27), start_time=time(8, 0), end_time=time(18, 0))
        self.days = [self.d1, self.d2, self.d3, self.d4]

        self.r1 = ResourceConfig(id=1, name="Quadra 1", is_active=True)
        self.r2 = ResourceConfig(id=2, name="Quadra 2", is_active=True)
        self.resources = [self.r1, self.r2]

    def test_basic_allocation_success(self):
        matches = [
            MatchRequest(id=1, modality_id=1, modality_name="Futsal", phase_code="GRUPO", time_a_id=10, time_b_id=20, duration_minutes=50, buffer_minutes=10),
            MatchRequest(id=2, modality_id=1, modality_name="Futsal", phase_code="GRUPO", time_a_id=30, time_b_id=40, duration_minutes=50, buffer_minutes=10),
        ]
        solver = ScheduleSolver(
            days=self.days,
            resources=self.resources,
            phase_constraints=[],
            matches=matches
        )
        result = solver.solve()
        self.assertTrue(result.success)
        self.assertEqual(len(result.allocations), 2)

    def test_strict_phase_date_restriction(self):
        """
        Regra 1 e 3: Semifinal apenas em 26/09 e Final apenas em 27/09.
        Mesmo que haja espaço livre em 19/09 e 20/09, a semifinal DEVE ficar em 26/09 e final em 27/09.
        """
        phase_constraints = [
            PhaseConstraint(phase_code="SEMI", phase_name="Semifinal", allowed_dates={date(2026, 9, 26)}),
            PhaseConstraint(phase_code="FINAL", phase_name="Final", allowed_dates={date(2026, 9, 27)}),
        ]
        matches = [
            MatchRequest(id=1, modality_id=1, modality_name="Futsal", phase_code="GRUPO", time_a_id=1, time_b_id=2, duration_minutes=50, buffer_minutes=10, precedence_order=1),
            MatchRequest(id=2, modality_id=1, modality_name="Futsal", phase_code="SEMI", time_a_id=3, time_b_id=4, duration_minutes=50, buffer_minutes=10, precedence_order=2),
            MatchRequest(id=3, modality_id=1, modality_name="Futsal", phase_code="FINAL", time_a_id=5, time_b_id=6, duration_minutes=50, buffer_minutes=10, precedence_order=3),
        ]
        solver = ScheduleSolver(
            days=self.days,
            resources=self.resources,
            phase_constraints=phase_constraints,
            matches=matches
        )
        result = solver.solve()
        self.assertTrue(result.success)

        alloc_map = {a.match_id: a for a in result.allocations}
        self.assertEqual(alloc_map[2].date, date(2026, 9, 26))
        self.assertEqual(alloc_map[3].date, date(2026, 9, 27))

    def test_multi_date_allowed_phase(self):
        """
        Regra 7: Quartas de final com múltiplas datas permitidas (19/09 ou 20/09).
        """
        phase_constraints = [
            PhaseConstraint(phase_code="QUARTAS", phase_name="Quartas", allowed_dates={date(2026, 9, 19), date(2026, 9, 20)}),
        ]
        matches = [
            MatchRequest(id=1, modality_id=1, modality_name="Vôlei", phase_code="QUARTAS", time_a_id=1, time_b_id=2),
            MatchRequest(id=2, modality_id=1, modality_name="Vôlei", phase_code="QUARTAS", time_a_id=3, time_b_id=4),
        ]
        solver = ScheduleSolver(
            days=self.days,
            resources=self.resources,
            phase_constraints=phase_constraints,
            matches=matches
        )
        result = solver.solve()
        self.assertTrue(result.success)
        for a in result.allocations:
            self.assertIn(a.date, [date(2026, 9, 19), date(2026, 9, 20)])

    def test_team_concurrency_and_rest_interval(self):
        """
        Garante que uma mesma equipe na mesma modalidade não jogue simultaneamente e respeite o tempo de descanso mínimo.
        """
        # Time 10 jogando duas partidas da mesma modalidade (Futsal)
        matches = [
            MatchRequest(id=1, modality_id=1, modality_name="Futsal", phase_code="G", time_a_id=10, time_b_id=20, duration_minutes=60, buffer_minutes=0),
            MatchRequest(id=2, modality_id=1, modality_name="Futsal", phase_code="G", time_a_id=10, time_b_id=30, duration_minutes=60, buffer_minutes=0),
        ]
        # 1 dia, 2 quadras disponíveis ao mesmo tempo (08:00 às 18:00)
        solver = ScheduleSolver(
            days=[self.d1],
            resources=[self.r1, self.r2],
            phase_constraints=[],
            matches=matches,
            min_team_rest_minutes=60
        )
        result = solver.solve()
        self.assertTrue(result.success)
        a1, a2 = result.allocations[0], result.allocations[1]
        
        # Datetimes não podem se sobrepor e a diferença entre fim de um e início do outro deve ser >= 60 min
        dt1_start = datetime.combine(a1.date, a1.start_time)
        dt1_end = datetime.combine(a1.date, a1.end_time)
        dt2_start = datetime.combine(a2.date, a2.start_time)
        dt2_end = datetime.combine(a2.date, a2.end_time)

        if dt1_start < dt2_start:
            self.assertGreaterEqual((dt2_start - dt1_end).total_seconds() / 60, 60)
        else:
            self.assertGreaterEqual((dt1_start - dt2_end).total_seconds() / 60, 60)

    def test_delegation_multi_modality_concurrency_allowed(self):
        """
        Garante que a mesma delegação pode disputar modalidades diferentes simultaneamente
        em quadras diferentes (já que são times/atletas distintos).
        """
        # Delegação 10 jogando Futsal e Basquete no mesmo horário
        matches = [
            MatchRequest(id=1, modality_id=1, modality_name="Futsal", phase_code="G", time_a_id=10, time_b_id=20, duration_minutes=60, buffer_minutes=0),
            MatchRequest(id=2, modality_id=2, modality_name="Basquete", phase_code="G", time_a_id=10, time_b_id=30, duration_minutes=60, buffer_minutes=0),
        ]
        solver = ScheduleSolver(
            days=[self.d1],
            resources=[self.r1, self.r2],
            phase_constraints=[],
            matches=matches,
            min_team_rest_minutes=60
        )
        result = solver.solve()
        self.assertTrue(result.success)
        self.assertEqual(len(result.allocations), 2)
        
        # Podem começar no mesmo horário inicial porque são modalidades diferentes
        alloc_map = {a.match_id: a for a in result.allocations}
        self.assertEqual(alloc_map[1].start_time, time(8, 0))
        self.assertEqual(alloc_map[2].start_time, time(8, 0))
        self.assertNotEqual(alloc_map[1].resource_id, alloc_map[2].resource_id)

    def test_phase_dependency_precedence(self):
        """
        Regra 6: Partida de Quartas precede Semifinal.
        """
        matches = [
            MatchRequest(id=1, modality_id=1, modality_name="Futsal", phase_code="QUARTAS", time_a_id=1, time_b_id=2, duration_minutes=60, buffer_minutes=0, precedence_order=1),
            MatchRequest(id=2, modality_id=1, modality_name="Futsal", phase_code="SEMI", time_a_id=None, time_b_id=None, depends_on_match_ids=[1], duration_minutes=60, buffer_minutes=0, precedence_order=2),
        ]
        solver = ScheduleSolver(
            days=[self.d1],  # Mesmo dia
            resources=[self.r1],
            phase_constraints=[],
            matches=matches,
            min_team_rest_minutes=30
        )
        result = solver.solve()
        self.assertTrue(result.success)
        alloc_map = {a.match_id: a for a in result.allocations}
        q = alloc_map[1]
        s = alloc_map[2]
        
        # A semifinal deve começar estritamente após a quarta terminar + descanso
        q_end = datetime.combine(q.date, q.end_time)
        s_start = datetime.combine(s.date, s.start_time)
        self.assertGreaterEqual(s_start, q_end)

    def test_max_daily_matches_per_team_constraint(self):
        """
        Garante que uma equipe não ultrapasse o limite diário de jogos (ex: máx 2 jogos por dia).
        Se a equipe tem 3 jogos e há 2 dias disponíveis, o 3º jogo DEVE ir para o 2º dia.
        """
        matches = [
            MatchRequest(id=1, modality_id=1, modality_name="Futsal", phase_code="G", time_a_id=10, time_b_id=20, duration_minutes=50, buffer_minutes=10),
            MatchRequest(id=2, modality_id=1, modality_name="Futsal", phase_code="G", time_a_id=10, time_b_id=30, duration_minutes=50, buffer_minutes=10),
            MatchRequest(id=3, modality_id=1, modality_name="Futsal", phase_code="G", time_a_id=10, time_b_id=40, duration_minutes=50, buffer_minutes=10),
        ]
        # 2 dias disponíveis, 1 quadra, max 2 jogos por dia
        solver = ScheduleSolver(
            days=[self.d1, self.d2],
            resources=[self.r1],
            phase_constraints=[],
            matches=matches,
            min_team_rest_minutes=30,
            max_daily_matches_per_team=2
        )
        result = solver.solve()
        self.assertTrue(result.success)
        
        # Conta jogos no dia 1 e dia 2
        d1_matches = [a for a in result.allocations if a.date == self.d1.date]
        d2_matches = [a for a in result.allocations if a.date == self.d2.date]
        self.assertLessEqual(len(d1_matches), 2)
        self.assertGreaterEqual(len(d2_matches), 1)

    def test_net_sport_contiguous_grouping_on_shared_court(self):
        """
        Garante que em uma mesma quadra compartilhada, os jogos de Vôlei fiquem agrupados
        em sequência contínua (sem intercalar Vôlei -> Futsal -> Vôlei).
        """
        matches = [
            MatchRequest(id=1, modality_id=1, modality_name="Voleibol Masc", phase_code="G", time_a_id=1, time_b_id=2, duration_minutes=50, buffer_minutes=10),
            MatchRequest(id=2, modality_id=2, modality_name="Futsal", phase_code="G", time_a_id=3, time_b_id=4, duration_minutes=50, buffer_minutes=10),
            MatchRequest(id=3, modality_id=1, modality_name="Voleibol Fem", phase_code="G", time_a_id=5, time_b_id=6, duration_minutes=50, buffer_minutes=10),
        ]
        solver = ScheduleSolver(
            days=[self.d1],
            resources=[self.r1],
            phase_constraints=[],
            matches=matches,
            min_team_rest_minutes=10,
            group_net_sports=True
        )
        result = solver.solve()
        self.assertTrue(result.success)

        # Ordena alocações por horário de início
        ordered = sorted(result.allocations, key=lambda a: a.start_time)
        types = [a.match_request.is_net_sport for a in ordered]
        
        # Verifica número de alternâncias de tipo
        transitions = sum(1 for i in range(1, len(types)) if types[i] != types[i-1])
        self.assertLessEqual(transitions, 1, "Vôlei deve acontecer em bloco contínuo na quadra")
