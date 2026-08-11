import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from core.models import (
    Modalidade, Campus, Atleta, InscricaoModalidade, Inscricao,
    ChaveamentoModalidade, PartidaChaveamento, Jogo, PreSumula,
    RegistroDisciplinarAtleta, CartaoPartida
)
from core.disciplinar_services import (
    registrar_cartao_atleta, remover_cartao_atleta,
    recalcular_disciplinar_atleta_modalidade, processar_cumprimento_suspensao_partida
)
from core.chaveamento_services import registrar_resultado_partida

User = get_user_model()


class ModuloDisciplinarTests(TestCase):
    def setUp(self):
        self.comissao = User.objects.create_user(
            email='comissao@ufvjm.edu.br',
            role='COMISSAO',
            is_staff=True
        )

        self.delegacao_a = User.objects.create_user(
            email='delegacao_a@ufvjm.edu.br',
            nome_delegacao='Delegação Alfa',
            role='REPRESENTANTE',
            status_delegacao='deferido',
            perfil_completo=True,
            cpf='366.146.971-10'
        )

        self.delegacao_b = User.objects.create_user(
            email='delegacao_b@ufvjm.edu.br',
            nome_delegacao='Delegação Beta',
            role='REPRESENTANTE',
            status_delegacao='deferido',
            perfil_completo=True,
            cpf='181.498.521-23'
        )

        self.campus = Campus.objects.create(nome='Diamantina')

        # Modalidades
        self.futsal = Modalidade.objects.create(
            nome='Futsal Masculino',
            genero='M',
            inscricoes_abertas=True
        )
        self.handebol = Modalidade.objects.create(
            nome='Handebol Masculino',
            genero='M',
            inscricoes_abertas=True
        )

        # Atletas
        self.atleta1 = Atleta.objects.create(
            nome_completo='João da Silva',
            cadastrado_por=self.delegacao_a,
            campus=self.campus,
            em_conformidade=True
        )
        self.atleta2 = Atleta.objects.create(
            nome_completo='Pedro Santos',
            cadastrado_por=self.delegacao_a,
            campus=self.campus,
            em_conformidade=True
        )

        # Inscreve os atletas nas modalidades
        insc_a = Inscricao.objects.create(delegacao=self.delegacao_a, status='deferido')
        for mod in [self.futsal, self.handebol]:
            im_a = InscricaoModalidade.objects.create(inscricao=insc_a, modalidade=mod)
            im_a.atletas.add(self.atleta1, self.atleta2)

        # Chaveamento Futsal
        self.chaveamento_futsal = ChaveamentoModalidade.objects.create(
            modalidade=self.futsal
        )

        # Partidas de Futsal
        self.partida1 = PartidaChaveamento.objects.create(
            chaveamento=self.chaveamento_futsal,
            fase='GRUPO',
            time_a=self.delegacao_a,
            time_b=self.delegacao_b
        )
        self.partida2 = PartidaChaveamento.objects.create(
            chaveamento=self.chaveamento_futsal,
            fase='GRUPO',
            time_a=self.delegacao_a,
            time_b=self.delegacao_b
        )
        self.partida3 = PartidaChaveamento.objects.create(
            chaveamento=self.chaveamento_futsal,
            fase='GRUPO',
            time_a=self.delegacao_a,
            time_b=self.delegacao_b
        )

    def test_cartao_amarelo_simples(self):
        """1 Cartão amarelo -> acumula 1, sem suspensão."""
        registrar_cartao_atleta(self.partida1, self.atleta1, 'AMARELO')

        reg = RegistroDisciplinarAtleta.objects.get(atleta=self.atleta1, modalidade=self.futsal)
        self.assertEqual(reg.cartoes_amarelos_acumulados, 1)
        self.assertEqual(reg.suspenso_jogos_pendentes, 0)
        self.assertFalse(reg.esta_suspenso)

    def test_segundo_amarelo_acumulado_gera_suspensao_e_zera_acumulo(self):
        """2º Amarelo em partidas diferentes -> 1 jogo de suspensão, acúmulo zerado."""
        registrar_cartao_atleta(self.partida1, self.atleta1, 'AMARELO')
        registrar_cartao_atleta(self.partida2, self.atleta1, 'AMARELO')

        reg = RegistroDisciplinarAtleta.objects.get(atleta=self.atleta1, modalidade=self.futsal)
        self.assertEqual(reg.cartoes_amarelos_acumulados, 0)  # Zerado após gerar suspensão
        self.assertEqual(reg.suspenso_jogos_pendentes, 1)
        self.assertTrue(reg.esta_suspenso)
        self.assertEqual(reg.total_amarelos_historico, 2)

    def test_cumprimento_de_suspensao_em_partida_concluida(self):
        """Atleta suspenso cumpre a suspensão na partida seguinte finalizada da sua equipe."""
        # Gera suspensão por 2 amarelos
        registrar_cartao_atleta(self.partida1, self.atleta1, 'AMARELO')
        registrar_cartao_atleta(self.partida2, self.atleta1, 'AMARELO')

        # Finaliza partida 2
        registrar_resultado_partida(self.partida2, 2, 1)

        reg = RegistroDisciplinarAtleta.objects.get(atleta=self.atleta1, modalidade=self.futsal)
        self.assertEqual(reg.suspenso_jogos_pendentes, 1)

        # Partida 3 é jogada sem o atleta1 (sem cartões nele) e finalizada
        registrar_resultado_partida(self.partida3, 1, 0)

        reg.refresh_from_db()
        self.assertEqual(reg.suspenso_jogos_pendentes, 0)
        self.assertFalse(reg.esta_suspenso)
        self.assertEqual(reg.total_jogos_suspensao_cumpridos, 1)

    def test_cartao_vermelho_direto(self):
        """Cartão vermelho direto -> 1 jogo de suspensão. Histórico de amarelos permanece intacto."""
        registrar_cartao_atleta(self.partida1, self.atleta1, 'AMARELO')
        registrar_cartao_atleta(self.partida2, self.atleta1, 'VERMELHO')

        reg = RegistroDisciplinarAtleta.objects.get(atleta=self.atleta1, modalidade=self.futsal)
        self.assertEqual(reg.cartoes_amarelos_acumulados, 1)  # Permanece 1!
        self.assertEqual(reg.suspenso_jogos_pendentes, 1)
        self.assertEqual(reg.total_vermelhos_historico, 1)

    def test_segundo_amarelo_na_mesma_partida(self):
        """Lançar 'AMARELO' 2 vezes no mesmo jogo -> sistema converte 2º para 'SEGUNDO_AMARELO' (expulsão + 1 jogo suspensão)."""
        c1 = registrar_cartao_atleta(self.partida1, self.atleta1, 'AMARELO', minuto=10)
        c2 = registrar_cartao_atleta(self.partida1, self.atleta1, 'AMARELO', minuto=35)

        self.assertEqual(c1.tipo, 'AMARELO')
        self.assertEqual(c2.tipo, 'SEGUNDO_AMARELO')

        reg = RegistroDisciplinarAtleta.objects.get(atleta=self.atleta1, modalidade=self.futsal)
        self.assertEqual(reg.suspenso_jogos_pendentes, 1)
        self.assertEqual(reg.total_vermelhos_historico, 1)

    def test_isolamento_de_suspensao_por_modalidade(self):
        """Suspensão em Futsal NÃO pode suspender o atleta em Handebol."""
        registrar_cartao_atleta(self.partida1, self.atleta1, 'VERMELHO')

        reg_futsal = RegistroDisciplinarAtleta.objects.get(atleta=self.atleta1, modalidade=self.futsal)
        reg_handebol = RegistroDisciplinarAtleta.objects.filter(atleta=self.atleta1, modalidade=self.handebol).first()

        self.assertTrue(reg_futsal.esta_suspenso)
        self.assertFalse(reg_handebol and reg_handebol.esta_suspenso)

    def test_bloqueio_escalacao_presumula_atleta_suspenso(self):
        """Garante que atleta suspenso é impedido de ser escalado via API de pré-súmulas."""
        # Cria Jogo
        jogo = Jogo.objects.create(
            modalidade=self.futsal,
            data_jogo='2026-08-15',
            time_a=self.delegacao_a,
            time_b=self.delegacao_b
        )

        # Suspende atleta1
        registrar_cartao_atleta(self.partida1, self.atleta1, 'VERMELHO')

        self.client.force_login(self.delegacao_a)
        response = self.client.post(
            '/api/presumulas/',
            data=json.dumps({
                'jogo_id': jogo.id,
                'atletas': [{'atleta_id': self.atleta1.id, 'camisa': 10}],
                'tecnico': 'Técnico Teste'
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        res_data = response.json()
        self.assertIn('suspenso', res_data.get('error', '').lower())

    def test_escalacao_atleta_liberado_sucesso(self):
        """Atleta sem suspensão consegue ser escalado normalmente."""
        jogo = Jogo.objects.create(
            modalidade=self.futsal,
            data_jogo='2026-08-15',
            time_a=self.delegacao_a,
            time_b=self.delegacao_b
        )

        self.client.force_login(self.delegacao_a)
        response = self.client.post(
            '/api/presumulas/',
            data=json.dumps({
                'jogo_id': jogo.id,
                'atletas': [{'atleta_id': self.atleta2.id, 'camisa': 7}],
                'tecnico': 'Técnico Teste'
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))

    def test_cartao_atleta_fora_da_partida_rejeitado(self):
        """Tentar registrar cartão para um atleta de uma delegação que não joga a partida lança ValueError."""
        delegacao_c = User.objects.create_user(
            email='delegacao_c@ufvjm.edu.br',
            nome_delegacao='Delegação Gama',
            role='REPRESENTANTE',
            status_delegacao='deferido',
            perfil_completo=True,
            cpf='529.982.247-25'
        )
        atleta_fora = Atleta.objects.create(
            nome_completo='Atleta de Outra Delegação',
            email='fora@ufvjm.edu.br',
            matricula='999999',
            curso='Curso X',
            campus=self.campus,
            cadastrado_por=delegacao_c
        )
        insc = Inscricao.objects.create(delegacao=delegacao_c)
        im = InscricaoModalidade.objects.create(inscricao=insc, modalidade=self.futsal)
        im.atletas.add(atleta_fora)

        with self.assertRaises(ValueError) as ctx:
            registrar_cartao_atleta(self.partida1, atleta_fora, 'AMARELO')
        self.assertIn("não pertence às delegações desta partida", str(ctx.exception))

    def test_atletas_time_a_e_b_retornam_apenas_equipes_da_partida(self):
        """Verifica se atletas_time_a e atletas_time_b retornam somente os atletas da respectiva delegação cadastrados na modalidade."""
        atleta_b = Atleta.objects.create(
            nome_completo='Carlos Oliveira',
            cadastrado_por=self.delegacao_b,
            campus=self.campus,
            em_conformidade=True
        )
        insc_b = Inscricao.objects.create(delegacao=self.delegacao_b, status='deferido')
        im_b = InscricaoModalidade.objects.create(inscricao=insc_b, modalidade=self.futsal)
        im_b.atletas.add(atleta_b)

        atletas_a = list(self.partida1.atletas_time_a)
        atletas_b = list(self.partida1.atletas_time_b)

        self.assertIn(self.atleta1, atletas_a)
        self.assertNotIn(atleta_b, atletas_a)

        self.assertIn(atleta_b, atletas_b)
        self.assertNotIn(self.atleta1, atletas_b)
