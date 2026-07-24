from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.models import (
    Modalidade, Campus, Atleta, Inscricao, InscricaoModalidade, Jogo,
    ChaveamentoModalidade, GrupoChaveamento, TimeGrupo, PartidaChaveamento
)
from core.chaveamento_services import (
    gerar_chaveamento_modalidade,
    registrar_resultado_partida,
    encerrar_fase_grupos_e_gerar_mata_mata
)

User = get_user_model()

# Lista de CPFs válidos únicos para testes
VALID_CPFS = [
    "52998224725", "05844883011", "11144477735", "22255588800", "33366699988",
    "44477700066", "55588811144", "66699922222", "77700033300", "88811144488",
    "99922255566", "12345678909", "98765432100", "11111111111", "22222222222"
]
def generate_valid_cpf(index):
    base = f"{100000000 + index}"
    s1 = sum(int(base[i]) * (10 - i) for i in range(9))
    d1 = 0 if (s1 % 11) < 2 else 11 - (s1 % 11)
    s2 = sum(int(base[i]) * (11 - i) for i in range(9)) + d1 * 2
    d2 = 0 if (s2 % 11) < 2 else 11 - (s2 % 11)
    return f"{base}{d1}{d2}"

cpf_counter = 0

class ChaveamentoModuleTestCase(TestCase):
    def setUp(self):
        global cpf_counter
        cpf_counter = 0
        # Create or Get Campuses
        self.campus_dia, _ = Campus.objects.get_or_create(nome="Campus Diamantina")
        self.campus_muc, _ = Campus.objects.get_or_create(nome="Campus Mucuri")
        self.campus_unai, _ = Campus.objects.get_or_create(nome="Campus Unaí")
        self.campus_jan, _ = Campus.objects.get_or_create(nome="Campus Janaúba")

        # Create Modalidade
        self.futsal = Modalidade.objects.create(
            nome="Futsal Masculino",
            genero="M",
            limite_minimo_jogadores=5,
            limite_maximo_jogadores=12
        )

        # Create Users for roles
        self.admin_user = User.objects.create_user(
            email="admin_comissao@ufvjm.edu.br",
            nome_completo="Admin Comissão",
            role="COMISSAO",
            is_staff=True
        )

        self.rep_user = self._create_delegation("rep_delegacao@ufvjm.edu.br", "Delegação Alfa", self.campus_dia)

    def _create_delegation(self, email, nome_del, campus):
        global cpf_counter
        cpf_counter += 1
        user_cpf = generate_valid_cpf(cpf_counter)
        user = User.objects.create_user(
            email=email,
            nome_completo=f"Rep {nome_del}",
            role="REPRESENTANTE",
            nome_delegacao=nome_del,
            cpf=user_cpf,
            status_delegacao="deferido"
        )

        atleta = Atleta.objects.create(
            nome_completo=f"Atleta {nome_del}",
            email=f"atleta_{email}",
            matricula="123456",
            curso="Ed. Física",
            campus=campus,
            cadastrado_por=user,
            em_conformidade=True
        )
        inscricao = Inscricao.objects.create(delegacao=user, status="deferido")
        im = InscricaoModalidade.objects.create(inscricao=inscricao, modalidade=self.futsal)
        im.atletas.add(atleta)
        return user

    def _create_delegation_for_mod(self, email, nome_del, campus, modalidade):
        global cpf_counter
        cpf_counter += 1
        user_cpf = generate_valid_cpf(cpf_counter)
        user = User.objects.create_user(
            email=email,
            nome_completo=f"Rep {nome_del}",
            role="REPRESENTANTE",
            nome_delegacao=nome_del,
            cpf=user_cpf,
            status_delegacao="deferido"
        )

        atleta = Atleta.objects.create(
            nome_completo=f"Atleta {nome_del}",
            email=f"atleta_{email}",
            matricula="123456",
            curso="Ed. Física",
            campus=campus,
            cadastrado_por=user,
            em_conformidade=True
        )
        inscricao = Inscricao.objects.create(delegacao=user, status="deferido")
        im = InscricaoModalidade.objects.create(inscricao=inscricao, modalidade=modalidade)
        im.atletas.add(atleta)
        return user

    def test_gerar_chaveamento_com_2_vagas_externas(self):
        """
        Métricas: 1 time de Mucuri, 1 time de Unaí, 1 time de Janaúba (Total ext = 2 vagas)
        Diamantina com 5 times (ímpar).
        """
        d_muc1 = self._create_delegation("muc1@ufvjm.edu.br", "Del Mucuri 1", self.campus_muc)
        d_unai = self._create_delegation("unai@ufvjm.edu.br", "Del Unaí 1", self.campus_unai)
        d_jan = self._create_delegation("jan@ufvjm.edu.br", "Del Janaúba 1", self.campus_jan)

        dia_teams = [
            self._create_delegation(f"dia{i}@ufvjm.edu.br", f"Del Diamantina {i}", self.campus_dia)
            for i in range(1, 6)
        ]

        chaveamento = gerar_chaveamento_modalidade(self.futsal)

        self.assertEqual(chaveamento.vagas_externas, 2)
        self.assertEqual(chaveamento.fase_atual, 'fase_grupos')

        # Grupos gerados
        grupos = list(chaveamento.grupos.all())
        self.assertTrue(len(grupos) >= 2)

        # Atualiza classificados e preenche mata-mata
        encerrar_fase_grupos_e_gerar_mata_mata(chaveamento)

        partidas_mata_mata = PartidaChaveamento.objects.filter(chaveamento=chaveamento)
        fases = set(p.fase for p in partidas_mata_mata)

        self.assertIn('SEMI_GERAL', fases)
        self.assertIn('FINAL_GERAL', fases)
        self.assertIn('BRONZE', fases)

    def test_registrar_resultado_e_progressao(self):
        """
        Testa o registro de resultado de uma partida e a propagação automática para a próxima fase.
        """
        d1 = self._create_delegation("d1@ufvjm.edu.br", "Time Alpha", self.campus_dia)
        d2 = self._create_delegation("d2@ufvjm.edu.br", "Time Beta", self.campus_dia)

        chaveamento = ChaveamentoModalidade.objects.create(modalidade=self.futsal, fase_atual='mata_mata_local')

        final = PartidaChaveamento.objects.create(
            chaveamento=chaveamento,
            fase='FINAL_GERAL'
        )

        semi = PartidaChaveamento.objects.create(
            chaveamento=chaveamento,
            fase='SEMI_GERAL',
            time_a=d1,
            time_b=d2,
            proxima_partida=final,
            posicao_proxima_partida='A'
        )

        # Registra vitória do Time Alpha (d1) por 3 x 1
        registrar_resultado_partida(semi, 3, 1)

        semi.refresh_from_db()
        final.refresh_from_db()

        self.assertTrue(semi.finalizada)
        self.assertEqual(semi.vencedor, d1)
        self.assertEqual(semi.perdedor, d2)
        self.assertEqual(final.time_a, d1)

    def test_views_comissao(self):
        """
        Testa permissões e renderização do painel da comissão organizadora.
        """
        self.client.force_login(self.admin_user)

        # 1. Admin List
        res = self.client.get(reverse('chaveamento_admin_list'))
        self.assertEqual(res.status_code, 200)

        # 2. Gerar Chaveamento
        res_post = self.client.post(reverse('chaveamento_gerar', kwargs={'pk': self.futsal.pk}))
        self.assertEqual(res_post.status_code, 302)

        # 3. Admin Detail
        res_detail = self.client.get(reverse('chaveamento_admin_detail', kwargs={'pk': self.futsal.pk}))
        self.assertEqual(res_detail.status_code, 200)

        # 4. Resetar Chaveamento
        res_reset = self.client.post(reverse('chaveamento_resetar', kwargs={'pk': self.futsal.pk}))
        self.assertEqual(res_reset.status_code, 302)
        self.assertFalse(ChaveamentoModalidade.objects.filter(modalidade=self.futsal).exists())

    def test_views_delegacao(self):
        """
        Testa renderização das telas públicas para as delegações.
        """
        self.client.force_login(self.rep_user)

        # 1. Public List
        res = self.client.get(reverse('chaveamento_public_list'))
        self.assertEqual(res.status_code, 200)

        # 2. Gera chaveamento
        gerar_chaveamento_modalidade(self.futsal)

        # 3. Public Detail
        res_detail = self.client.get(reverse('chaveamento_public_detail', kwargs={'pk': self.futsal.pk}))
        self.assertEqual(res_detail.status_code, 200)

    def test_gerar_chaveamento_1_sede_1_externo_direto_final(self):
        """
        Caso excepcional: 1 time da sede (Diamantina) e 1 time de fora (Mucuri).
        Ambos devem ir direto para a Grande Final Geral sem grupos, semifinais ou repescagem.
        """
        modalidade_teste = Modalidade.objects.create(
            nome="Vôlei de Praia Masculino",
            genero="M",
            limite_minimo_jogadores=2,
            limite_maximo_jogadores=4
        )
        d_dia = self._create_delegation_for_mod("dia_unico@ufvjm.edu.br", "Del Diamantina Único", self.campus_dia, modalidade_teste)
        d_muc = self._create_delegation_for_mod("muc_unico@ufvjm.edu.br", "Del Mucuri Único", self.campus_muc, modalidade_teste)

        chaveamento = gerar_chaveamento_modalidade(modalidade_teste)

        # 1. Não deve haver grupos criados
        self.assertEqual(chaveamento.grupos.count(), 0)

        # 2. Deve existir exatamente 1 partida (FINAL_GERAL)
        partidas = chaveamento.partidas.all()
        self.assertEqual(partidas.count(), 1)

        final_geral = partidas.first()
        self.assertEqual(final_geral.fase, 'FINAL_GERAL')
        self.assertEqual(final_geral.time_a, d_dia)
        self.assertEqual(final_geral.time_b, d_muc)

        # 3. Não deve haver semifinais, repescagem ou quartas
        fases = set(partidas.values_list('fase', flat=True))
        self.assertNotIn('SEMI_GERAL', fases)
        self.assertNotIn('SEMI_LOCAL', fases)
        self.assertNotIn('BRONZE', fases)
        self.assertNotIn('DISPUTA_3_LOCAL', fases)
        self.assertNotIn('QUARTAS_LOCAL', fases)

        # 4. Deve sincronizar com a tabela Jogo
        self.assertIsNotNone(final_geral.jogo)
        self.assertEqual(final_geral.jogo.time_a, d_dia)
        self.assertEqual(final_geral.jogo.time_b, d_muc)

