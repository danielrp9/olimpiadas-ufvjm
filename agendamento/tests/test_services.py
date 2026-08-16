from datetime import date, time
from django.test import TestCase
from django.contrib.auth import get_user_model

from core.models import Modalidade, ChaveamentoModalidade, PartidaChaveamento, Jogo
from agendamento.models import (
    ConfiguracaoGeral, DataDisponivel, RecursoLocal,
    RestricaoFase, CenarioExecucao, ItemAlocacao
)
from agendamento.services import (
    obter_ou_criar_configuracao, executar_agendamento,
    aplicar_cenario_ao_oficial
)

User = get_user_model()


class ScheduleServicesTests(TestCase):
    """
    Testes de integração para a camada de serviços do módulo de agendamento.
    """

    def setUp(self):
        self.user_a = User.objects.create_user(email="a@ufvjm.edu.br", nome_delegacao="Delegação A")
        self.user_b = User.objects.create_user(email="b@ufvjm.edu.br", nome_delegacao="Delegação B")
        self.user_c = User.objects.create_user(email="c@ufvjm.edu.br", nome_delegacao="Delegação C")
        self.user_d = User.objects.create_user(email="d@ufvjm.edu.br", nome_delegacao="Delegação D")

        self.mod = Modalidade.objects.create(nome="Futsal", genero="M")
        self.chaveamento = ChaveamentoModalidade.objects.create(modalidade=self.mod, fase_atual="fase_geral")

        self.p_semi1 = PartidaChaveamento.objects.create(
            chaveamento=self.chaveamento,
            fase="SEMI_LOCAL",
            time_a=self.user_a,
            time_b=self.user_b
        )
        self.p_semi2 = PartidaChaveamento.objects.create(
            chaveamento=self.chaveamento,
            fase="SEMI_LOCAL",
            time_a=self.user_c,
            time_b=self.user_d
        )
        self.p_final = PartidaChaveamento.objects.create(
            chaveamento=self.chaveamento,
            fase="FINAL_LOCAL",
            time_a=None,
            time_b=None
        )
        # Final depende das semis
        self.p_semi1.proxima_partida = self.p_final
        self.p_semi1.save()
        self.p_semi2.proxima_partida = self.p_final
        self.p_semi2.save()

        # Configuração de agendamento
        self.config = obter_ou_criar_configuracao()
        self.data_semis = DataDisponivel.objects.create(
            configuracao=self.config,
            data=date(2026, 9, 26),
            horario_inicio=time(8, 0),
            horario_fim=time(18, 0),
            ativo=True
        )
        self.data_final = DataDisponivel.objects.create(
            configuracao=self.config,
            data=date(2026, 9, 27),
            horario_inicio=time(8, 0),
            horario_fim=time(18, 0),
            ativo=True
        )

        self.quadra = RecursoLocal.objects.create(
            configuracao=self.config,
            nome="Ginásio Poliesportivo",
            ativo=True
        )
        self.quadra.modalidades_permitidas.add(self.mod)

        # Restrições de datas por fase
        rf_semi = self.config.restricoes_fases.get(fase_codigo="SEMI_LOCAL")
        rf_semi.datas_permitidas.add(self.data_semis)

        rf_final = self.config.restricoes_fases.get(fase_codigo="FINAL_LOCAL")
        rf_final.datas_permitidas.add(self.data_final)

    def test_executar_e_aplicar_cenario(self):
        # 1. Executa o agendamento
        cenario = executar_agendamento(self.config, titulo="Teste Oficial")
        self.assertEqual(cenario.status, 'sucesso')
        self.assertEqual(cenario.alocacoes.count(), 3)

        # Verifica datas alocadas
        aloc_semi1 = cenario.alocacoes.get(partida_chaveamento=self.p_semi1)
        aloc_semi2 = cenario.alocacoes.get(partida_chaveamento=self.p_semi2)
        aloc_final = cenario.alocacoes.get(partida_chaveamento=self.p_final)

        self.assertEqual(aloc_semi1.data_alocada, date(2026, 9, 26))
        self.assertEqual(aloc_semi2.data_alocada, date(2026, 9, 26))
        self.assertEqual(aloc_final.data_alocada, date(2026, 9, 27))

        # 2. Aplica o cenário ao oficial
        total_atualizados, msgs = aplicar_cenario_ao_oficial(cenario)
        self.assertGreaterEqual(total_atualizados, 3)

        # Recarrega partidas do banco
        self.p_semi1.refresh_from_db()
        self.p_semi2.refresh_from_db()
        self.p_final.refresh_from_db()

        self.assertEqual(self.p_semi1.data_partida, date(2026, 9, 26))
        self.assertEqual(self.p_semi2.data_partida, date(2026, 9, 26))
        self.assertEqual(self.p_final.data_partida, date(2026, 9, 27))
        
        # Verifica se os Jogos foram criados e sincronizados com quadra
        self.assertIsNotNone(self.p_semi1.jogo)
        self.assertEqual(self.p_semi1.jogo.data_jogo, date(2026, 9, 26))
        self.assertEqual(self.p_semi1.jogo.local, "Ginásio Poliesportivo")

        # 3. Testa o reset completo de horários e quadras
        from agendamento.services import resetar_todos_horarios
        total_resetadas = resetar_todos_horarios(self.config)
        self.assertGreaterEqual(total_resetadas, 3)

        self.p_semi1.refresh_from_db()
        self.p_semi2.refresh_from_db()
        self.p_final.refresh_from_db()

        self.assertIsNone(self.p_semi1.data_partida)
        self.assertIsNone(self.p_semi1.horario_partida)
        self.assertIsNone(self.p_final.data_partida)
        self.assertIsNone(self.p_final.horario_partida)

        # Verifica que o jogo teve local e horário zerados
        if self.p_semi1.jogo:
            self.p_semi1.jogo.refresh_from_db()
            self.assertIsNone(self.p_semi1.jogo.horario_jogo)
            self.assertIsNone(self.p_semi1.jogo.local)
