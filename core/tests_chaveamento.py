from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.models import (
    Modalidade, Campus, Atleta, Inscricao, InscricaoModalidade, Jogo,
    ChaveamentoModalidade, GrupoChaveamento, TimeGrupo, PartidaChaveamento, SetPartida
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
        Ambos devem ir direto para a Grande Final Geral sem grupos locais, semifinais ou repescagem.
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

        # 1. Não deve haver fase de grupos local criada para Diamantina
        self.assertEqual(chaveamento.grupos.filter(tipo='grupo_local').count(), 0)

        # 2. Deve existir exatamente 1 partida na arvore de mata-mata/geral (FINAL_GERAL)
        partidas_mata_mata = chaveamento.partidas.filter(grupo__isnull=True)
        self.assertEqual(partidas_mata_mata.count(), 1)

        final_geral = partidas_mata_mata.first()
        self.assertEqual(final_geral.fase, 'FINAL_GERAL')
        self.assertEqual(final_geral.time_a, d_dia)
        self.assertEqual(final_geral.time_b, d_muc)

        # 3. Não deve haver semifinais, repescagem ou quartas
        fases = set(partidas_mata_mata.values_list('fase', flat=True))
        self.assertNotIn('SEMI_GERAL', fases)
        self.assertNotIn('SEMI_LOCAL', fases)
        self.assertNotIn('BRONZE', fases)
        self.assertNotIn('DISPUTA_3_LOCAL', fases)
        self.assertNotIn('QUARTAS_LOCAL', fases)

        # 4. Deve sincronizar com a tabela Jogo
        self.assertIsNotNone(final_geral.jogo)
        self.assertEqual(final_geral.jogo.time_a, d_dia)
        self.assertEqual(final_geral.jogo.time_b, d_muc)

    def test_gerar_chaveamento_1_sede_2_externos_eliminatoria(self):
        """
        Cenário real (ex: Basquete Feminino):
        - 1 time de Diamantina (sede)
        - 2 times de Mucuri (que disputam eliminatória externa por 1 vaga no confronto final)
        Resultado esperado:
        - Eliminatória Externa para Mucuri
        - Sem fase de grupos para Diamantina
        - Árvore de Mata-Mata contendo APENAS a Grande Final Geral (sem semifinais, finais locais ou bronze)
        - O vencedor da eliminatória externa avança diretamente para a Grande Final Geral.
        """
        basquete_fem = Modalidade.objects.create(
            nome="Basquete Feminino",
            genero="F",
            limite_minimo_jogadores=5,
            limite_maximo_jogadores=12
        )
        d_dia = self._create_delegation_for_mod("atletica_macabra@ufvjm.edu.br", "Atlética Macabra", self.campus_dia, basquete_fem)
        d_muc1 = self._create_delegation_for_mod("flamejante@ufvjm.edu.br", "Flamejante", self.campus_muc, basquete_fem)
        d_muc2 = self._create_delegation_for_mod("preguica@ufvjm.edu.br", "Preguiça Doida", self.campus_muc, basquete_fem)

        chaveamento = gerar_chaveamento_modalidade(basquete_fem)

        # 1. Sem grupo local para Diamantina
        self.assertEqual(chaveamento.grupos.filter(tipo='grupo_local').count(), 0)

        # 2. Eliminatória Externa de Mucuri criada
        grupo_muc = chaveamento.grupos.filter(tipo='eliminatoria_ext').first()
        self.assertIsNotNone(grupo_muc)
        self.assertEqual(grupo_muc.partidas.count(), 1)
        partida_elim = grupo_muc.partidas.first()

        # 3. Árvore de Mata-Mata tem APENAS a Grande Final Geral
        partidas_mata_mata = chaveamento.partidas.filter(grupo__isnull=True)
        self.assertEqual(partidas_mata_mata.count(), 1)

        final_geral = partidas_mata_mata.first()
        self.assertEqual(final_geral.fase, 'FINAL_GERAL')
        self.assertEqual(final_geral.time_a, d_dia)
        self.assertIsNone(final_geral.time_b) # Aguarda vencedor da eliminatória

        # 4. A partida eliminatória externa deve apontar para a Grande Final Geral
        self.assertEqual(partida_elim.proxima_partida, final_geral)
        self.assertEqual(partida_elim.posicao_proxima_partida, 'B')

        # 5. Ao registrar o resultado da eliminatória, o vencedor deve ir direto para a final
        registrar_resultado_partida(partida_elim, 28, 20)
        final_geral.refresh_from_db()
        self.assertEqual(final_geral.time_b, d_muc1)

    def test_excecao_1_handebol_feminino_5_dia_1_ext(self):
        """
        Teste 1 — Handebol Feminino excepcional (5 Diamantina + 1 Externo)
        Esperado: 1 grupo com 5 equipes, 3 classificados, sem mata-mata local,
        3 equipes na Fase Geral + 1 externa.
        Valida que 4º e 5º não são classificados e que os perdedores das Semis Gerais vão para o Bronze.
        """
        handebol_fem = Modalidade.objects.create(
            nome="Handebol Feminino",
            genero="F",
            limite_minimo_jogadores=7,
            limite_maximo_jogadores=14
        )
        d_muc = self._create_delegation_for_mod("h_muc@ufvjm.edu.br", "Del Mucuri Hand", self.campus_muc, handebol_fem)
        d_dias = [
            self._create_delegation_for_mod(f"h_dia{i}@ufvjm.edu.br", f"Del Dia Hand {i}", self.campus_dia, handebol_fem)
            for i in range(1, 6)
        ]

        chaveamento = gerar_chaveamento_modalidade(handebol_fem)

        # 1. Deve haver exatamente 1 grupo de Diamantina com 5 equipes
        grupos_locais = chaveamento.grupos.filter(tipo='grupo_local')
        self.assertEqual(grupos_locais.count(), 1)
        grupo_unico = grupos_locais.first()
        self.assertEqual(grupo_unico.times.count(), 5)
        self.assertEqual(grupo_unico.vagas_classificacao, 3)

        # 2. NÃO deve ser criado mata-mata local de Diamantina
        self.assertEqual(chaveamento.partidas.filter(fase__in=['QUARTAS_LOCAL', 'SEMI_LOCAL', 'FINAL_LOCAL']).count(), 0)

        # 3. Deve haver Semifinais Gerais criadas
        semis_geral = chaveamento.partidas.filter(fase='SEMI_GERAL').order_by('id')
        self.assertEqual(semis_geral.count(), 2)

        # 4. Finalizar todas as partidas do grupo único atribuindo vitórias determinísticas para d_dias[0] > d_dias[1] > d_dias[2] > d_dias[3] > d_dias[4]
        partidas = list(grupo_unico.partidas.all())
        for p in partidas:
            # Pega índice dos times d_dias
            idx_a = d_dias.index(p.time_a)
            idx_b = d_dias.index(p.time_b)
            if idx_a < idx_b:
                registrar_resultado_partida(p, 10, 5)
            else:
                registrar_resultado_partida(p, 5, 10)

        chaveamento.refresh_from_db()
        encerrar_fase_grupos_e_gerar_mata_mata(chaveamento)

        # 5. Valida classificação do grupo: exatamente 3 classificados (1º, 2º e 3º), 4º e 5º NÃO classificados
        times_ordenados = list(grupo_unico.times.order_by('-pontos', '-vitorias', '-saldo_gols', '-gols_pro'))
        self.assertTrue(times_ordenados[0].classificado)
        self.assertTrue(times_ordenados[1].classificado)
        self.assertTrue(times_ordenados[2].classificado)
        self.assertFalse(times_ordenados[3].classificado)
        self.assertFalse(times_ordenados[4].classificado)

        self.assertEqual(times_ordenados[0].delegacao, d_dias[0])
        self.assertEqual(times_ordenados[1].delegacao, d_dias[1])
        self.assertEqual(times_ordenados[2].delegacao, d_dias[2])

        sg1 = semis_geral[0]
        sg2 = semis_geral[1]
        sg1.refresh_from_db()
        sg2.refresh_from_db()

        self.assertEqual(sg1.time_a, d_dias[0]) # 1º Diamantina
        self.assertEqual(sg1.time_b, d_muc)     # 1º Externo
        self.assertEqual(sg2.time_a, d_dias[1]) # 2º Diamantina
        self.assertEqual(sg2.time_b, d_dias[2]) # 3º Diamantina

        # 6. Simula realização das Semifinais Gerais e verifica progressão para Final Geral e Chave Bronze
        registrar_resultado_partida(sg1, 15, 10) # Vencedor d_dias[0], Perdedor d_muc
        registrar_resultado_partida(sg2, 12, 14) # Vencedor d_dias[2], Perdedor d_dias[1]

        final_geral = chaveamento.partidas.filter(fase='FINAL_GERAL').first()
        bronze = chaveamento.partidas.filter(fase='BRONZE').first()

        final_geral.refresh_from_db()
        bronze.refresh_from_db()

        self.assertEqual(final_geral.time_a, d_dias[0])
        self.assertEqual(final_geral.time_b, d_dias[2])
        self.assertEqual(bronze.time_a, d_muc)
        self.assertEqual(bronze.time_b, d_dias[1])

    def test_excecao_2_tenis_de_mesa_feminino_7_dia_2_ext(self):
        """
        Teste 2 — Tênis de Mesa Feminino excepcional (7 Diamantina + 2 Externos)
        Esperado: 2 grupos (4 + 3), exatamente 2 classificados por grupo (total 4),
        Mata-mata local, Campeão + Vice nas Semifinais Gerais com os 2 externos.
        Simula fluxo completo até as Semifinais Gerais.
        """
        tm_fem = Modalidade.objects.create(
            nome="Tênis de Mesa Feminino",
            genero="F",
            limite_minimo_jogadores=1,
            limite_maximo_jogadores=2
        )
        d_muc = self._create_delegation_for_mod("tm_muc@ufvjm.edu.br", "Del Mucuri TM", self.campus_muc, tm_fem)
        d_unai = self._create_delegation_for_mod("tm_unai@ufvjm.edu.br", "Del Unaí TM", self.campus_unai, tm_fem)
        d_dias = [
            self._create_delegation_for_mod(f"tm_dia{i}@ufvjm.edu.br", f"Del Dia TM {i}", self.campus_dia, tm_fem)
            for i in range(1, 8)
        ]

        chaveamento = gerar_chaveamento_modalidade(tm_fem)

        # 1. Duas vagas externas e 2 grupos locais
        self.assertEqual(chaveamento.vagas_externas, 2)
        grupos_locais = list(chaveamento.grupos.filter(tipo='grupo_local').order_by('nome'))
        self.assertEqual(len(grupos_locais), 2)

        g_a = grupos_locais[0]
        g_b = grupos_locais[1]

        # Exatamente 2 vagas por grupo
        self.assertEqual(g_a.vagas_classificacao, 2)
        self.assertEqual(g_b.vagas_classificacao, 2)

        # 2. Registra resultados de todas as partidas dos grupos
        for g in grupos_locais:
            partidas = list(g.partidas.all())
            for p in partidas:
                # Time A vence sempre
                registrar_resultado_partida(p, 3, 0)

        chaveamento.refresh_from_db()
        encerrar_fase_grupos_e_gerar_mata_mata(chaveamento)

        # Valida que em cada grupo EXATAMENTE 2 são classificados
        self.assertEqual(g_a.times.filter(classificado=True).count(), 2)
        self.assertEqual(g_b.times.filter(classificado=True).count(), 2)

        # 3. Mata-mata local deve ter Semifinais locais preenchidas
        semis_local = list(chaveamento.partidas.filter(fase='SEMI_LOCAL').order_by('id'))
        self.assertEqual(len(semis_local), 2)
        self.assertIsNotNone(semis_local[0].time_a)
        self.assertIsNotNone(semis_local[0].time_b)
        self.assertIsNotNone(semis_local[1].time_a)
        self.assertIsNotNone(semis_local[1].time_b)

        # 4. Executa Semifinais locais e Final local de Diamantina
        sl1, sl2 = semis_local[0], semis_local[1]
        registrar_resultado_partida(sl1, 3, 1) # Winner sl1.time_a
        registrar_resultado_partida(sl2, 3, 2) # Winner sl2.time_a

        final_local = chaveamento.partidas.filter(fase='FINAL_LOCAL').first()
        self.assertIsNotNone(final_local)
        final_local.refresh_from_db()
        self.assertEqual(final_local.time_a, sl1.time_a)
        self.assertEqual(final_local.time_b, sl2.time_a)

        # Executa Final Local
        registrar_resultado_partida(final_local, 3, 0) # Winner sl1.time_a (Campeão), Perdedor sl2.time_a (Vice)

        # 5. Verifica avanço para Semifinais Gerais
        semis_geral = list(chaveamento.partidas.filter(fase='SEMI_GERAL').order_by('id'))
        self.assertEqual(len(semis_geral), 2)

        sg1, sg2 = semis_geral[0], semis_geral[1]
        sg1.refresh_from_db()
        sg2.refresh_from_db()

        self.assertEqual(sg1.time_a, sl1.time_a) # Campeão Diamantina
        self.assertEqual(sg1.time_b, d_muc)      # Externo 1
        self.assertEqual(sg2.time_a, sl2.time_a) # Vice Diamantina
        self.assertEqual(sg2.time_b, d_unai)     # Externo 2

    def test_handebol_fora_da_condicao_excepcional(self):
        """
        Teste 3 — Handebol Feminino fora da condição (ex: 6 Diamantina + 1 Externo)
        Esperado: utilizar a regra padrão existente.
        """
        handebol_fem = Modalidade.objects.create(
            nome="Handebol Feminino",
            genero="F",
            limite_minimo_jogadores=7,
            limite_maximo_jogadores=14
        )
        d_muc = self._create_delegation_for_mod("h_muc2@ufvjm.edu.br", "Del Mucuri Hand 2", self.campus_muc, handebol_fem)
        d_dias = [
            self._create_delegation_for_mod(f"h_dia6_{i}@ufvjm.edu.br", f"Del Dia Hand6 {i}", self.campus_dia, handebol_fem)
            for i in range(1, 7)
        ]

        chaveamento = gerar_chaveamento_modalidade(handebol_fem)

        # Na regra padrão com 6 equipes em Diamantina: grupos de 3 + 3, com 2 vagas cada (4 no mata-mata local)
        grupos_locais = list(chaveamento.grupos.filter(tipo='grupo_local'))
        self.assertEqual(len(grupos_locais), 2)
        semis_local = chaveamento.partidas.filter(fase='SEMI_LOCAL')
        self.assertEqual(semis_local.count(), 2)

    def test_tenis_de_mesa_fora_da_condicao_excepcional(self):
        """
        Teste 4 — Tênis de Mesa Feminino fora da condição (ex: 7 Diamantina + 1 Externo)
        Esperado: utilizar a regra padrão existente (grupo de 4 passa 3, grupo de 3 passa 2 -> total 5).
        """
        tm_fem = Modalidade.objects.create(
            nome="Tênis de Mesa Feminino",
            genero="F",
            limite_minimo_jogadores=1,
            limite_maximo_jogadores=2
        )
        d_muc = self._create_delegation_for_mod("tm_muc1@ufvjm.edu.br", "Del Mucuri TM 1", self.campus_muc, tm_fem)
        d_dias = [
            self._create_delegation_for_mod(f"tm_dia7_{i}@ufvjm.edu.br", f"Del Dia TM7 {i}", self.campus_dia, tm_fem)
            for i in range(1, 8)
        ]

        chaveamento = gerar_chaveamento_modalidade(tm_fem)

        self.assertEqual(chaveamento.vagas_externas, 1)
        grupos_locais = list(chaveamento.grupos.filter(tipo='grupo_local'))
        vagas = [g.vagas_classificacao for g in grupos_locais]
        self.assertIn(3, vagas) # No padrão, grupo de 4 dá 3 vagas

    def test_outra_modalidade_padrao(self):
        """
        Teste 5 — Outra modalidade (Futsal Masculino)
        Esperado: chaveamento 100% de acordo com a regra padrão.
        """
        d_muc = self._create_delegation_for_mod("futsal_muc@ufvjm.edu.br", "Del Mucuri Futsal", self.campus_muc, self.futsal)
        d_dias = [
            self._create_delegation_for_mod(f"futsal_dia_{i}@ufvjm.edu.br", f"Del Dia Futsal {i}", self.campus_dia, self.futsal)
            for i in range(1, 6)
        ]

        chaveamento = gerar_chaveamento_modalidade(self.futsal)
        grupos_locais = list(chaveamento.grupos.filter(tipo='grupo_local'))
        self.assertEqual(len(grupos_locais), 2)

    def test_chaveamento_share_list_view_unauthenticated(self):
        """
        Testa se a lista pública de chaveamentos (/chaveamentos/compartilhar/)
        é acessível sem autenticação e lista as modalidades.
        """
        self.client.logout()
        res = self.client.get(reverse('chaveamento_share_list'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Chaveamentos")
        self.assertContains(res, self.futsal.nome)

    def test_chaveamento_share_view_unauthenticated(self):
        """
        Testa se a view de compartilhamento público (/chaveamento/compartilhar/<pk>/)
        é acessível por qualquer usuário não autenticado sem redirecionar para o login.
        """
        gerar_chaveamento_modalidade(self.futsal)
        self.client.logout()

        res = self.client.get(reverse('chaveamento_share', kwargs={'pk': self.futsal.pk}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Fase de Grupos e Classificatórias por Campus")
        self.assertContains(res, self.futsal.nome)

    def test_formato_3_grupos_melhor_segundo_geracao(self):
        """
        Testa a geração do formato específico (9 equipes em Diamantina, 3 grupos de 3,
        1 classificado direto por grupo + melhor 2º geral = 4 equipes, sem Quartas).
        """
        modalidade_queimada = Modalidade.objects.create(
            nome="Queimada Mista",
            genero="X",
            formato_chaveamento="formato_3_grupos_melhor_segundo",
            limite_minimo_jogadores=6,
            limite_maximo_jogadores=12
        )
        teams = [
            self._create_delegation_for_mod(f"queimada_dia_{i}@ufvjm.edu.br", f"Time Queimada {i}", self.campus_dia, modalidade_queimada)
            for i in range(1, 10)
        ]

        chaveamento = gerar_chaveamento_modalidade(modalidade_queimada)

        # 1. 3 grupos locais de 3 equipes cada
        grupos_locais = list(chaveamento.grupos.filter(tipo='grupo_local').order_by('nome'))
        self.assertEqual(len(grupos_locais), 3)
        for g in grupos_locais:
            self.assertEqual(g.times.count(), 3)
            self.assertEqual(g.vagas_classificacao, 1) # 1 vaga direta por grupo
            self.assertEqual(g.partidas.count(), 3) # Turno único: 3 partidas

        # 2. NÃO deve haver Quartas de Final
        fases = set(chaveamento.partidas.values_list('fase', flat=True))
        self.assertNotIn('QUARTAS_LOCAL', fases)

        # 3. Deve haver Semifinais locais (2 partidas), Final Local (1) e Disputa de 3º Lugar (1)
        self.assertEqual(chaveamento.partidas.filter(fase='SEMI_LOCAL').count(), 2)
        self.assertEqual(chaveamento.partidas.filter(fase='FINAL_LOCAL').count(), 1)
        self.assertEqual(chaveamento.partidas.filter(fase='DISPUTA_3_LOCAL').count(), 1)

    def test_formato_3_grupos_melhor_segundo_criterios_desempate(self):
        """
        Testa os critérios de desempate para escolha do melhor 2º colocado geral:
        1. maior número de vitórias;
        2. maior saldo de jogadores;
        3. maior número de jogadores adversários eliminados;
        4. menor número de jogadores da própria equipe eliminados;
        5. menor número de penalidades;
        6. sorteio.
        """
        from core.models import CartaoPartida
        modalidade_teste = Modalidade.objects.create(
            nome="Modalidade Especial",
            genero="M",
            formato_chaveamento="formato_3_grupos_melhor_segundo",
            limite_minimo_jogadores=5,
            limite_maximo_jogadores=10
        )
        teams = [
            self._create_delegation_for_mod(f"esp_dia_{i}@ufvjm.edu.br", f"Time Esp {i}", self.campus_dia, modalidade_teste)
            for i in range(1, 10)
        ]

        chaveamento = gerar_chaveamento_modalidade(modalidade_teste)
        grupos = list(chaveamento.grupos.filter(tipo='grupo_local').order_by('nome'))
        g_a, g_b, g_c = grupos[0], grupos[1], grupos[2]

        t_a = list(g_a.times.all().select_related('delegacao'))
        t_b = list(g_b.times.all().select_related('delegacao'))
        t_c = list(g_c.times.all().select_related('delegacao'))

        # Grupo A:
        # t_a[0] vence t_a[1] (10 x 0) e t_a[2] (10 x 0) -> 1º colocado (6 pts, 2V)
        # t_a[1] vence t_a[2] (10 x 5) -> 2º colocado (3 pts, 1V, 10 pro, 15 contra, saldo -5)
        p_a = list(g_a.partidas.all())
        for p in p_a:
            if {p.time_a, p.time_b} == {t_a[0].delegacao, t_a[1].delegacao}:
                if p.time_a == t_a[0].delegacao: registrar_resultado_partida(p, 10, 0)
                else: registrar_resultado_partida(p, 0, 10)
            elif {p.time_a, p.time_b} == {t_a[0].delegacao, t_a[2].delegacao}:
                if p.time_a == t_a[0].delegacao: registrar_resultado_partida(p, 10, 0)
                else: registrar_resultado_partida(p, 0, 10)
            elif {p.time_a, p.time_b} == {t_a[1].delegacao, t_a[2].delegacao}:
                if p.time_a == t_a[1].delegacao: registrar_resultado_partida(p, 10, 5)
                else: registrar_resultado_partida(p, 5, 10)

        # Grupo B:
        # t_b[0] vence t_b[1] (10 x 8) e t_b[2] (10 x 0) -> 1º colocado (6 pts, 2V)
        # t_b[1] vence t_b[2] (10 x 2) -> 2º colocado (3 pts, 1V, 18 pro, 12 contra, saldo +6)
        p_b = list(g_b.partidas.all())
        for p in p_b:
            if {p.time_a, p.time_b} == {t_b[0].delegacao, t_b[1].delegacao}:
                if p.time_a == t_b[0].delegacao: registrar_resultado_partida(p, 10, 8)
                else: registrar_resultado_partida(p, 8, 10)
            elif {p.time_a, p.time_b} == {t_b[0].delegacao, t_b[2].delegacao}:
                if p.time_a == t_b[0].delegacao: registrar_resultado_partida(p, 10, 0)
                else: registrar_resultado_partida(p, 0, 10)
            elif {p.time_a, p.time_b} == {t_b[1].delegacao, t_b[2].delegacao}:
                if p.time_a == t_b[1].delegacao: registrar_resultado_partida(p, 10, 2)
                else: registrar_resultado_partida(p, 2, 10)

        # Grupo C:
        # t_c[0] vence t_c[1] (10 x 5) e t_c[2] (10 x 0) -> 1º colocado (6 pts, 2V)
        # t_c[1] vence t_c[2] (10 x 4) -> 2º colocado (3 pts, 1V, 15 pro, 14 contra, saldo +1)
        p_c = list(g_c.partidas.all())
        for p in p_c:
            if {p.time_a, p.time_b} == {t_c[0].delegacao, t_c[1].delegacao}:
                if p.time_a == t_c[0].delegacao: registrar_resultado_partida(p, 10, 5)
                else: registrar_resultado_partida(p, 5, 10)
            elif {p.time_a, p.time_b} == {t_c[0].delegacao, t_c[2].delegacao}:
                if p.time_a == t_c[0].delegacao: registrar_resultado_partida(p, 10, 0)
                else: registrar_resultado_partida(p, 0, 10)
            elif {p.time_a, p.time_b} == {t_c[1].delegacao, t_c[2].delegacao}:
                if p.time_a == t_c[1].delegacao: registrar_resultado_partida(p, 10, 4)
                else: registrar_resultado_partida(p, 4, 10)

        chaveamento.refresh_from_db()
        encerrar_fase_grupos_e_gerar_mata_mata(chaveamento)

        # Valida que o 2º do Grupo B (t_b[1]) foi o escolhido como melhor 2º (maior saldo: +6 vs +1 e -5)
        self.assertTrue(TimeGrupo.objects.get(grupo=g_b, delegacao=t_b[1].delegacao).classificado)
        self.assertFalse(TimeGrupo.objects.get(grupo=g_a, delegacao=t_a[1].delegacao).classificado)
        self.assertFalse(TimeGrupo.objects.get(grupo=g_c, delegacao=t_c[1].delegacao).classificado)

        # Semifinais geradas sem repetir confrontos de grupos:
        # t_b[1] veio do Grupo B. Portanto, t_b[1] NÃO pode enfrentar o vencedor do Grupo B (t_b[0]).
        # Deve enfrentar o vencedor do Grupo A (t_a[0]) ou Grupo C (t_c[0]).
        semis = list(chaveamento.partidas.filter(fase='SEMI_LOCAL').order_by('id'))
        semi1_teams = {semis[0].time_a, semis[0].time_b}
        semi2_teams = {semis[1].time_a, semis[1].time_b}

        # Verifica que nenhum confronto repete jogo do mesmo grupo
        self.assertNotIn({t_b[0].delegacao, t_b[1].delegacao}, [semi1_teams, semi2_teams])
        self.assertNotIn({t_a[0].delegacao, t_a[1].delegacao}, [semi1_teams, semi2_teams])
        self.assertNotIn({t_c[0].delegacao, t_c[1].delegacao}, [semi1_teams, semi2_teams])

    def test_formato_3_grupos_desempate_por_penalidades(self):
        """
        Testa desempate do melhor 2º colocado por menor número de penalidades (cartões).
        """
        from core.models import CartaoPartida
        mod_penalidade = Modalidade.objects.create(
            nome="Queimada Penalidades",
            genero="X",
            formato_chaveamento="formato_3_grupos_melhor_segundo",
            limite_minimo_jogadores=5,
            limite_maximo_jogadores=10
        )
        teams = [
            self._create_delegation_for_mod(f"pen_dia_{i}@ufvjm.edu.br", f"Time Pen {i}", self.campus_dia, mod_penalidade)
            for i in range(1, 10)
        ]
        chaveamento = gerar_chaveamento_modalidade(mod_penalidade)
        grupos = list(chaveamento.grupos.filter(tipo='grupo_local').order_by('nome'))
        g_a, g_b, g_c = grupos[0], grupos[1], grupos[2]

        t_a = list(g_a.times.all().select_related('delegacao'))
        t_b = list(g_b.times.all().select_related('delegacao'))
        t_c = list(g_c.times.all().select_related('delegacao'))

        # Faz todos os 2º colocados empatarem perfeitamente em vitórias (1), saldo (0), pro (10), contra (10)
        for g, times in [(g_a, t_a), (g_b, t_b), (g_c, t_c)]:
            for p in g.partidas.all():
                if {p.time_a, p.time_b} == {times[0].delegacao, times[1].delegacao}:
                    if p.time_a == times[0].delegacao: registrar_resultado_partida(p, 10, 0)
                    else: registrar_resultado_partida(p, 0, 10)
                elif {p.time_a, p.time_b} == {times[0].delegacao, times[2].delegacao}:
                    if p.time_a == times[0].delegacao: registrar_resultado_partida(p, 10, 0)
                    else: registrar_resultado_partida(p, 0, 10)
                elif {p.time_a, p.time_b} == {times[1].delegacao, times[2].delegacao}:
                    if p.time_a == times[1].delegacao: registrar_resultado_partida(p, 10, 0)
                    else: registrar_resultado_partida(p, 0, 10)

        # Adiciona 2 cartões/penalidades para o 2º do grupo A e 1 para o 2º do grupo B, 0 para o grupo C
        p_ga = g_a.partidas.first()
        p_gb = g_b.partidas.first()
        atleta_a = t_a[1].delegacao.atletas.first()
        atleta_b = t_b[1].delegacao.atletas.first()

        CartaoPartida.objects.create(partida=p_ga, atleta=atleta_a, delegacao=t_a[1].delegacao, modalidade=mod_penalidade, tipo='AMARELO')
        CartaoPartida.objects.create(partida=p_ga, atleta=atleta_a, delegacao=t_a[1].delegacao, modalidade=mod_penalidade, tipo='AMARELO')
        CartaoPartida.objects.create(partida=p_gb, atleta=atleta_b, delegacao=t_b[1].delegacao, modalidade=mod_penalidade, tipo='AMARELO')

        encerrar_fase_grupos_e_gerar_mata_mata(chaveamento)

        # O 2º do Grupo C (0 cartões) deve ser o classificado como melhor 2º
        self.assertTrue(TimeGrupo.objects.get(grupo=g_c, delegacao=t_c[1].delegacao).classificado)
        self.assertFalse(TimeGrupo.objects.get(grupo=g_a, delegacao=t_a[1].delegacao).classificado)
        self.assertFalse(TimeGrupo.objects.get(grupo=g_b, delegacao=t_b[1].delegacao).classificado)

    def test_modalidade_padrao_com_9_times_preserva_quartas(self):
        """
        Garante que modalidades com formato='padrao' que tenham 9 equipes continuem utilizando
        a regra histórica (gerando Quartas de Final e 6 classificados locais).
        """
        mod_padrao_9 = Modalidade.objects.create(
            nome="Vôlei Padrão 9",
            genero="M",
            formato_chaveamento="padrao",
            limite_minimo_jogadores=6,
            limite_maximo_jogadores=12
        )
        teams = [
            self._create_delegation_for_mod(f"vol_dia_{i}@ufvjm.edu.br", f"Time Vol {i}", self.campus_dia, mod_padrao_9)
            for i in range(1, 10)
        ]
        chaveamento = gerar_chaveamento_modalidade(mod_padrao_9)
        fases = set(chaveamento.partidas.values_list('fase', flat=True))
        # Modalidade padrão com 9 times DEVE gerar QUARTAS_LOCAL
        self.assertIn('QUARTAS_LOCAL', fases)

    def test_formato_3_grupos_fluxo_mata_mata_e_repescagem(self):
        """
        Valida que no formato 3 grupos de 3:
        1. Vencedores das Semifinais avançam para a Final Local (FINAL_LOCAL).
        2. Perdedores das Semifinais vão para a disputa de 3º Lugar (DISPUTA_3_LOCAL).
        3. O registro de placar nas fases finais define o campeão e o 3º colocado.
        """
        modalidade_queimada = Modalidade.objects.create(
            nome="Queimada Mata Mata",
            genero="X",
            formato_chaveamento="formato_3_grupos_melhor_segundo",
            limite_minimo_jogadores=6,
            limite_maximo_jogadores=12
        )
        teams = [
            self._create_delegation_for_mod(f"qm_dia_{i}@ufvjm.edu.br", f"Time QM {i}", self.campus_dia, modalidade_queimada)
            for i in range(1, 10)
        ]

        chaveamento = gerar_chaveamento_modalidade(modalidade_queimada)
        grupos = list(chaveamento.grupos.filter(tipo='grupo_local').order_by('nome'))

        # Finaliza jogos da fase de grupos com vitórias simples
        for g in grupos:
            partidas = list(g.partidas.all())
            for p in partidas:
                registrar_resultado_partida(p, 10, 5)

        encerrar_fase_grupos_e_gerar_mata_mata(chaveamento)

        # Semifinais estão preenchidas
        semis = list(chaveamento.partidas.filter(fase='SEMI_LOCAL').order_by('id'))
        self.assertEqual(len(semis), 2)
        s1, s2 = semis[0], semis[1]
        self.assertIsNotNone(s1.time_a)
        self.assertIsNotNone(s1.time_b)
        self.assertIsNotNone(s2.time_a)
        self.assertIsNotNone(s2.time_b)

        # Executa Semifinal 1 (time_a vence)
        registrar_resultado_partida(s1, 15, 10)
        # Executa Semifinal 2 (time_a vence)
        registrar_resultado_partida(s2, 12, 8)

        final_local = chaveamento.partidas.filter(fase='FINAL_LOCAL').first()
        disputa_3 = chaveamento.partidas.filter(fase='DISPUTA_3_LOCAL').first()

        final_local.refresh_from_db()
        disputa_3.refresh_from_db()

        # Vencedores das semis estão na Final
        self.assertEqual(final_local.time_a, s1.time_a)
        self.assertEqual(final_local.time_b, s2.time_a)

        # Perdedores das semis estão na Disputa de 3º Lugar
        self.assertEqual(disputa_3.time_a, s1.time_b)
        self.assertEqual(disputa_3.time_b, s2.time_b)

        # Executa Final e Disputa de 3º Lugar
        registrar_resultado_partida(final_local, 20, 18)
        registrar_resultado_partida(disputa_3, 14, 12)

        final_local.refresh_from_db()
        disputa_3.refresh_from_db()

        self.assertEqual(final_local.vencedor, s1.time_a)
        self.assertEqual(final_local.perdedor, s2.time_a)
        self.assertEqual(disputa_3.vencedor, s1.time_b)
        self.assertEqual(disputa_3.perdedor, s2.time_b)

    def test_cruzamento_olimpico_dois_grupos_semifinais(self):
        """
        Garante que com 2 grupos e 2 classificados por grupo:
        - Semi 1: 1ºA x 2ºB
        - Semi 2: 1ºB x 2ºA
        - Equipes do mesmo grupo NUNCA se enfrentam nas semifinais.
        """
        mod = Modalidade.objects.create(
            nome="Handebol 2G",
            genero="M",
            formato_chaveamento="padrao",
            limite_minimo_jogadores=5,
            limite_maximo_jogadores=12
        )
        # Cria 6 times no campus local (3 no Grupo A, 3 no Grupo B)
        teams = [
            self._create_delegation_for_mod(f"hnd_{i}@ufvjm.edu.br", f"Time HND {i}", self.campus_dia, mod)
            for i in range(1, 7)
        ]
        chaveamento = gerar_chaveamento_modalidade(mod)
        grupos = list(chaveamento.grupos.filter(tipo='grupo_local').order_by('nome'))
        self.assertEqual(len(grupos), 2)
        g_a, g_b = grupos[0], grupos[1]

        # Força 2 vagas de classificação em cada grupo
        g_a.vagas_classificacao = 2
        g_a.save()
        g_b.vagas_classificacao = 2
        g_b.save()

        # Simula partidas do Grupo A:
        # Time A1 ganha de todos (6 pts), Time A2 ganha do Time A3 (3 pts), Time A3 perde todas (0 pts)
        t_a = list(g_a.times.all())
        t_a1, t_a2, t_a3 = t_a[0].delegacao, t_a[1].delegacao, t_a[2].delegacao

        for p in g_a.partidas.all():
            if (p.time_a == t_a1 and p.time_b == t_a2) or (p.time_b == t_a1 and p.time_a == t_a2):
                placar_1 = 20 if p.time_a == t_a1 else 10
                placar_2 = 10 if p.time_a == t_a1 else 20
                registrar_resultado_partida(p, placar_1, placar_2)
            elif (p.time_a == t_a1 and p.time_b == t_a3) or (p.time_b == t_a1 and p.time_a == t_a3):
                placar_1 = 20 if p.time_a == t_a1 else 10
                placar_2 = 10 if p.time_a == t_a1 else 20
                registrar_resultado_partida(p, placar_1, placar_2)
            else:
                placar_1 = 20 if p.time_a == t_a2 else 10
                placar_2 = 10 if p.time_a == t_a2 else 20
                registrar_resultado_partida(p, placar_1, placar_2)

        # Simula partidas do Grupo B:
        # Time B1 ganha de todos (6 pts), Time B2 ganha do Time B3 (3 pts), Time B3 perde todas (0 pts)
        t_b = list(g_b.times.all())
        t_b1, t_b2, t_b3 = t_b[0].delegacao, t_b[1].delegacao, t_b[2].delegacao

        for p in g_b.partidas.all():
            if (p.time_a == t_b1 and p.time_b == t_b2) or (p.time_b == t_b1 and p.time_a == t_b2):
                placar_1 = 20 if p.time_a == t_b1 else 10
                placar_2 = 10 if p.time_a == t_b1 else 20
                registrar_resultado_partida(p, placar_1, placar_2)
            elif (p.time_a == t_b1 and p.time_b == t_b3) or (p.time_b == t_b1 and p.time_a == t_b3):
                placar_1 = 20 if p.time_a == t_b1 else 10
                placar_2 = 10 if p.time_a == t_b1 else 20
                registrar_resultado_partida(p, placar_1, placar_2)
            else:
                placar_1 = 20 if p.time_a == t_b2 else 10
                placar_2 = 10 if p.time_a == t_b2 else 20
                registrar_resultado_partida(p, placar_1, placar_2)

        encerrar_fase_grupos_e_gerar_mata_mata(chaveamento)

        semis = list(chaveamento.partidas.filter(fase='SEMI_LOCAL').order_by('id'))
        self.assertEqual(len(semis), 2)
        s1, s2 = semis[0], semis[1]

        # Semi 1 deve ser 1ºA x 2ºB
        self.assertEqual(s1.time_a, t_a1)
        self.assertEqual(s1.time_b, t_b2)

        # Semi 2 deve ser 1ºB x 2ºA
        self.assertEqual(s2.time_a, t_b1)
        self.assertEqual(s2.time_b, t_a2)

        # Garante que equipes do mesmo grupo NÃO se enfrentam nas semifinais
        times_g_a = {t_a1, t_a2, t_a3}
        times_g_b = {t_b1, t_b2, t_b3}

        # Na Semi 1, um time deve ser do Grupo A e outro do Grupo B
        self.assertTrue(
            (s1.time_a in times_g_a and s1.time_b in times_g_b) or
            (s1.time_a in times_g_b and s1.time_b in times_g_a)
        )
        # Na Semi 2, um time deve ser do Grupo A e outro do Grupo B
        self.assertTrue(
            (s2.time_a in times_g_a and s2.time_b in times_g_b) or
            (s2.time_a in times_g_b and s2.time_b in times_g_a)
        )

    def test_cruzamento_dois_grupos_conclusao_parcial(self):
        """
        Garante que quando apenas um grupo é concluído (Grupo A):
        - Os times classificados do Grupo A NÃO se enfrentam prematuramente entre si.
        - Não é criado Jogo com times do mesmo grupo.
        - Quando o Grupo B encerra, os confrontos são completados com o cruzamento correto.
        """
        mod = Modalidade.objects.create(
            nome="Basquete 2G Parcial",
            genero="F",
            formato_chaveamento="padrao",
            limite_minimo_jogadores=5,
            limite_maximo_jogadores=12
        )
        teams = [
            self._create_delegation_for_mod(f"bsk_{i}@ufvjm.edu.br", f"Time BSK {i}", self.campus_dia, mod)
            for i in range(1, 7)
        ]
        chaveamento = gerar_chaveamento_modalidade(mod)
        grupos = list(chaveamento.grupos.filter(tipo='grupo_local').order_by('nome'))
        g_a, g_b = grupos[0], grupos[1]
        g_a.vagas_classificacao = 2
        g_a.save()
        g_b.vagas_classificacao = 2
        g_b.save()

        # Conclui apenas partidas do Grupo A
        t_a = list(g_a.times.all())
        t_a1, t_a2, t_a3 = t_a[0].delegacao, t_a[1].delegacao, t_a[2].delegacao

        for p in g_a.partidas.all():
            registrar_resultado_partida(p, 15, 10)

        # Não finaliza partidas do Grupo B (estão em andamento)
        from core.chaveamento_services import atualizar_classificados_e_preencher_mata_mata
        atualizar_classificados_e_preencher_mata_mata(chaveamento)

        semis = list(chaveamento.partidas.filter(fase='SEMI_LOCAL').order_by('id'))
        s1, s2 = semis[0], semis[1]

        # Em Semi 1, 1ºA aguarda 2ºB (que ainda é None)
        self.assertIsNotNone(s1.time_a)
        self.assertIsNone(s1.time_b)

        # Em Semi 2, 2ºA aguarda 1ºB (que ainda é None)
        self.assertIsNone(s2.time_a)
        self.assertIsNotNone(s2.time_b)

        # Garante que 1ºA e 2ºA não foram colocados na mesma semifinal
        self.assertNotEqual(s1.time_a, s1.time_b)
        self.assertNotEqual(s2.time_a, s2.time_b)

        # Nenhum jogo vinculado foi criado prematuramente para s1 ou s2 porque falta oponente
        self.assertIsNone(s1.jogo)
        self.assertIsNone(s2.jogo)

        # Agora finaliza o Grupo B
        for p in g_b.partidas.all():
            registrar_resultado_partida(p, 20, 10)

        s1.refresh_from_db()
        s2.refresh_from_db()

        # Agora ambas as semifinais estão completas com adversários cruzados
        self.assertIsNotNone(s1.time_a)
        self.assertIsNotNone(s1.time_b)
        self.assertIsNotNone(s2.time_a)
        self.assertIsNotNone(s2.time_b)

        # E agora os Jogos foram sincronizados corretamente
        self.assertIsNotNone(s1.jogo)
        self.assertIsNotNone(s2.jogo)
        self.assertEqual(s1.jogo.time_a, s1.time_a)
        self.assertEqual(s1.jogo.time_b, s1.time_b)

    def test_cruzamento_olimpico_dois_grupos_quartas(self):
        """
        Garante que quando há Quartas de Final em formato com 2 grupos (ex: 3 classificados por grupo):
        - Q1: 1ºA x Bye
        - Q2: 2ºB x 3ºA (Cruzamento de grupos, e NÃO 1ºB x 2ºB)
        - Q3: 1ºB x Bye
        - Q4: 2ºA x 3ºB (Cruzamento de grupos)
        - NUNCA há confronto entre equipes do mesmo grupo nas Quartas.
        """
        mod = Modalidade.objects.create(
            nome="Futsal 2G Quartas",
            genero="M",
            formato_chaveamento="padrao",
            limite_minimo_jogadores=5,
            limite_maximo_jogadores=12
        )
        teams = [
            self._create_delegation_for_mod(f"futq_{i}@ufvjm.edu.br", f"Time FUTQ {i}", self.campus_dia, mod)
            for i in range(1, 9)
        ]
        chaveamento = gerar_chaveamento_modalidade(mod)
        grupos = list(chaveamento.grupos.filter(tipo='grupo_local').order_by('nome'))
        g_a, g_b = grupos[0], grupos[1]

        # Define 3 vagas em cada grupo (total 6 classificados locais -> Quartas com 2 Byes)
        g_a.vagas_classificacao = 3
        g_a.save()
        g_b.vagas_classificacao = 3
        g_b.save()

        # Finaliza todas as partidas dos grupos
        for p in g_a.partidas.all():
            registrar_resultado_partida(p, 5, 2)
        for p in g_b.partidas.all():
            registrar_resultado_partida(p, 4, 1)

        encerrar_fase_grupos_e_gerar_mata_mata(chaveamento)

        quartas = list(chaveamento.partidas.filter(fase='QUARTAS_LOCAL').order_by('id'))
        self.assertEqual(len(quartas), 4)

        q1, q2, q3, q4 = quartas[0], quartas[1], quartas[2], quartas[3]

        c_a = [tg.delegacao for tg in g_a.times.filter(classificado=True).order_by('-pontos', '-vitorias', '-saldo_gols', '-gols_pro')]
        c_b = [tg.delegacao for tg in g_b.times.filter(classificado=True).order_by('-pontos', '-vitorias', '-saldo_gols', '-gols_pro')]

        # Q1: 1ºA tem Bye
        self.assertEqual(q1.time_a, c_a[0])
        self.assertTrue(q1.finalizada)
        self.assertEqual(q1.vencedor, c_a[0])

        # Q2: 2ºB x 3ºA (Cruzamento de grupos!)
        self.assertEqual(q2.time_a, c_b[1])
        self.assertEqual(q2.time_b, c_a[2])

        # Q3: 1ºB tem Bye
        self.assertEqual(q3.time_a, c_b[0])
        self.assertTrue(q3.finalizada)
        self.assertEqual(q3.vencedor, c_b[0])

        # Q4: 2ºA x 3ºB (Cruzamento de grupos!)
        self.assertEqual(q4.time_a, c_a[1])
        self.assertEqual(q4.time_b, c_b[2])

        # Semifinais já receberam os Byes de 1ºA e 1ºB
        semis = list(chaveamento.partidas.filter(fase='SEMI_LOCAL').order_by('id'))
        self.assertEqual(semis[0].time_a, c_a[0])
        self.assertEqual(semis[1].time_a, c_b[0])

    def test_preservacao_partidas_finalizadas(self):
        """
        Garante que partidas de mata-mata que já foram finalizadas não tenham seus dados
        sobrescritos ao recalcular os chaveamentos.
        """
        mod = Modalidade.objects.create(
            nome="Volei Preservado",
            genero="M",
            formato_chaveamento="padrao",
            limite_minimo_jogadores=6,
            limite_maximo_jogadores=12
        )
        teams = [
            self._create_delegation_for_mod(f"vol_p_{i}@ufvjm.edu.br", f"Time VP {i}", self.campus_dia, mod)
            for i in range(1, 7)
        ]
        chaveamento = gerar_chaveamento_modalidade(mod)
        for g in chaveamento.grupos.filter(tipo='grupo_local'):
            g.vagas_classificacao = 2
            g.save()
            for p in g.partidas.all():
                registrar_resultado_partida(p, 25, 20)

        encerrar_fase_grupos_e_gerar_mata_mata(chaveamento)

        semis = list(chaveamento.partidas.filter(fase='SEMI_LOCAL').order_by('id'))
        s1 = semis[0]
        # Joga a semifinal 1 e finaliza
        registrar_resultado_partida(s1, 25, 18)
        s1.refresh_from_db()
        vencedor_original = s1.vencedor
        self.assertTrue(s1.finalizada)

        # Chama atualizar_classificados_e_preencher_mata_mata novamente
        from core.chaveamento_services import atualizar_classificados_e_preencher_mata_mata
        atualizar_classificados_e_preencher_mata_mata(chaveamento)

        s1.refresh_from_db()
        # Garante que s1 continua finalizada com o mesmo vencedor e placar
        self.assertTrue(s1.finalizada)
        self.assertEqual(s1.vencedor, vencedor_original)
        self.assertEqual(s1.placar_a, 25)
        self.assertEqual(s1.placar_b, 18)

    def test_view_admin_e_publica_atualizam_automaticamente(self):
        """
        Garante que acessar as views de detalhe do chaveamento (admin e pública)
        aciona a atualização automática dos classificados e mata-mata.
        """
        mod = Modalidade.objects.create(
            nome="Peteca Auto Update",
            genero="M",
            formato_chaveamento="padrao",
            limite_minimo_jogadores=2,
            limite_maximo_jogadores=4
        )
        teams = [
            self._create_delegation_for_mod(f"pet_{i}@ufvjm.edu.br", f"Time PET {i}", self.campus_dia, mod)
            for i in range(1, 7)
        ]
        chaveamento = gerar_chaveamento_modalidade(mod)
        for g in chaveamento.grupos.filter(tipo='grupo_local'):
            g.vagas_classificacao = 2
            g.save()
            for p in g.partidas.all():
                registrar_resultado_partida(p, 21, 15)

        # Acessa a view de admin
        self.client.force_login(self.admin_user)
        resp_admin = self.client.get(reverse('chaveamento_admin_detail', args=[mod.pk]))
        self.assertEqual(resp_admin.status_code, 200)

        # Verifica que as semifinais estão preenchidas no contexto
        partidas_fase = resp_admin.context['partidas_por_fase']
        self.assertEqual(len(partidas_fase['SEMI_LOCAL']), 2)
        s1 = partidas_fase['SEMI_LOCAL'][0]
        self.assertIsNotNone(s1.time_a)
        self.assertIsNotNone(s1.time_b)

        # Acessa a view pública
        self.client.force_login(self.rep_user)
        resp_pub = self.client.get(reverse('chaveamento_public_detail', args=[mod.pk]))
        self.assertEqual(resp_pub.status_code, 200)

        # Acessa a view de compartilhamento (anônima)
        self.client.logout()
        resp_share = self.client.get(reverse('chaveamento_share', args=[mod.pk]))
        self.assertEqual(resp_share.status_code, 200)

    def test_wo_desclassifica_time_e_prioriza_time_sem_wo(self):
        """
        Garante que quando um time tem W.O., ele JAMAIS segue para a fase seguinte (classificado=False),
        e o sistema prioriza outro time sem W.O. (mesmo com menos pontos).
        """
        mod = Modalidade.objects.create(
            nome="Truco Teste WO",
            genero="M",
            limite_minimo_jogadores=2,
            limite_maximo_jogadores=4
        )
        t_a = self._create_delegation_for_mod("wo_t1@ufvjm.edu.br", "Time WO 1", self.campus_dia, mod)
        t_b = self._create_delegation_for_mod("wo_t2@ufvjm.edu.br", "Time WO 2", self.campus_dia, mod)
        t_c = self._create_delegation_for_mod("wo_t3@ufvjm.edu.br", "Time WO 3", self.campus_dia, mod)

        chaveamento = gerar_chaveamento_modalidade(mod)
        grupo = chaveamento.grupos.filter(tipo='grupo_local').first()
        grupo.vagas_classificacao = 2
        grupo.save()

        # Partidas do grupo
        # Partida 1: Time A vence Time B (Time A tem 3 pts, 0 WO)
        p1 = grupo.partidas.filter(time_a__in=[t_a, t_b], time_b__in=[t_a, t_b]).first()
        registrar_resultado_partida(p1, placar_a=12, placar_b=6)

        # Partida 2: Time A comete W.O. contra Time C (Time A recebe W.O.)
        p2 = grupo.partidas.filter(time_a__in=[t_a, t_c], time_b__in=[t_a, t_c]).first()
        if p2.time_a == t_a:
            registrar_resultado_partida(p2, placar_a=0, placar_b=1, wo_tipo='TIME_A', motivo_wo='Ausência')
        else:
            registrar_resultado_partida(p2, placar_a=1, placar_b=0, wo_tipo='TIME_B', motivo_wo='Ausência')

        # Partida 3: Time B vence Time C
        p3 = grupo.partidas.filter(time_a__in=[t_b, t_c], time_b__in=[t_b, t_c]).first()
        registrar_resultado_partida(p3, placar_a=12, placar_b=4)

        from core.chaveamento_services import atualizar_classificados_e_preencher_mata_mata
        atualizar_classificados_e_preencher_mata_mata(chaveamento)

        tg_a = TimeGrupo.objects.get(grupo=grupo, delegacao=t_a)
        tg_b = TimeGrupo.objects.get(grupo=grupo, delegacao=t_b)
        tg_c = TimeGrupo.objects.get(grupo=grupo, delegacao=t_c)

        self.assertEqual(tg_a.quantidade_wo, 1)
        self.assertEqual(tg_b.quantidade_wo, 0)
        self.assertEqual(tg_c.quantidade_wo, 0)

        # Time A tem 3 pontos mas tem W.O. -> NÃO pode se classificar!
        self.assertFalse(tg_a.classificado)
        # Time B e Time C não têm W.O. -> classificados!
        self.assertTrue(tg_b.classificado)
        self.assertTrue(tg_c.classificado)

        # Na ordenação do grupo, o time com W.O. fica no final
        times_ord = list(grupo.times.all())
        self.assertEqual(times_ord[-1].delegacao, t_a)

    def test_cenario_truco_grupos_com_wo_repescagem_e_vagas_completas(self):
        """
        Cenário real do Truco:
        - 11 times em Diamantina -> 3 Grupos: Grupo A (4), Grupo B (4), Grupo C (3).
        - Vagas originais: 3 em A, 3 em B, 2 em C (Total = 8 classificados para Quartas).
        - No Grupo A, 2 equipes cometem W.O. (restando apenas 2 equipes elegíveis).
        - O sistema deve desconsiderar os times com W.O. e priorizar equipes sem W.O. dos demais grupos.
        - Garante que exatamente 8 equipes avancem, nenhuma com W.O., e que as Quartas sejam preenchidas.
        """
        mod = Modalidade.objects.create(
            nome="Truco Geral 11 Times",
            genero="M",
            limite_minimo_jogadores=2,
            limite_maximo_jogadores=4
        )
        dia_teams = [
            self._create_delegation_for_mod(f"truco_{i}@ufvjm.edu.br", f"Dupla Truco {i}", self.campus_dia, mod)
            for i in range(1, 12)
        ]

        chaveamento = gerar_chaveamento_modalidade(mod)
        grupos = list(chaveamento.grupos.filter(tipo='grupo_local').order_by('nome'))
        self.assertEqual(len(grupos), 3)

        g_a, g_b, g_c = grupos[0], grupos[1], grupos[2]
        # Garante configuração padrão: Grupo A (4 times, vagas=3), B (4 times, vagas=3), C (3 times, vagas=2)
        g_a.vagas_classificacao = 3
        g_a.save()
        g_b.vagas_classificacao = 3
        g_b.save()
        g_c.vagas_classificacao = 2
        g_c.save()

        times_a = list(g_a.times.all())
        times_b = list(g_b.times.all())
        times_c = list(g_c.times.all())

        # No Grupo A:
        # times_a[0] e times_a[1] jogam normalmente e não têm WO.
        # times_a[2] e times_a[3] cometem WO em suas partidas!
        for p in g_a.partidas.all():
            if p.time_a == times_a[2].delegacao or p.time_b == times_a[2].delegacao:
                wo_side = 'TIME_A' if p.time_a == times_a[2].delegacao else 'TIME_B'
                registrar_resultado_partida(p, 0, 1, wo_tipo=wo_side, motivo_wo='WO')
            elif p.time_a == times_a[3].delegacao or p.time_b == times_a[3].delegacao:
                wo_side = 'TIME_A' if p.time_a == times_a[3].delegacao else 'TIME_B'
                registrar_resultado_partida(p, 0, 1, wo_tipo=wo_side, motivo_wo='WO')
            else:
                registrar_resultado_partida(p, 12, 8)

        # No Grupo B e Grupo C: todos jogam normalmente (zero W.O.)
        for p in g_b.partidas.all():
            registrar_resultado_partida(p, 12, 10)
        for p in g_c.partidas.all():
            registrar_resultado_partida(p, 12, 10)

        from core.chaveamento_services import atualizar_classificados_e_preencher_mata_mata
        atualizar_classificados_e_preencher_mata_mata(chaveamento)

        # Validações:
        # 1. Times com WO no Grupo A JAMAIS são classificados
        self.assertFalse(TimeGrupo.objects.get(id=times_a[2].id).classificado)
        self.assertFalse(TimeGrupo.objects.get(id=times_a[3].id).classificado)
        self.assertGreater(TimeGrupo.objects.get(id=times_a[2].id).quantidade_wo, 0)
        self.assertGreater(TimeGrupo.objects.get(id=times_a[3].id).quantidade_wo, 0)

        # 2. Total de classificados em Diamantina deve ser EXATAMENTE 8
        total_classificados = TimeGrupo.objects.filter(grupo__in=grupos, classificado=True).count()
        self.assertEqual(total_classificados, 8)

        # 3. NENHUM classificado tem WO
        classificados = TimeGrupo.objects.filter(grupo__in=grupos, classificado=True)
        for tg in classificados:
            self.assertEqual(tg.quantidade_wo, 0)

        # 4. As Quartas de Final devem estar 100% preenchidas com as 8 equipes (4 partidas x 2 equipes)
        quartas = list(chaveamento.partidas.filter(fase='QUARTAS_LOCAL').order_by('id'))
        self.assertEqual(len(quartas), 4)
        for q in quartas:
            self.assertIsNotNone(q.time_a)
            self.assertIsNotNone(q.time_b)
            self.assertNotEqual(q.time_a, q.time_b)

        # 5. Visualização na view exibe badge de Desclassificado
        self.client.force_login(self.admin_user)
        resp = self.client.get(reverse('chaveamento_admin_detail', args=[mod.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Desclassificado")

    def _setup_modalidade_com_quartas(self, prefix="man"):
        mod = Modalidade.objects.create(
            nome=f"Modalidade Manual {prefix}",
            genero="M",
            formato_chaveamento="padrao",
            limite_minimo_jogadores=5,
            limite_maximo_jogadores=12
        )
        teams = [
            self._create_delegation_for_mod(f"{prefix}_{i}@ufvjm.edu.br", f"Time {prefix.upper()} {i}", self.campus_dia, mod)
            for i in range(1, 9)
        ]
        chaveamento = gerar_chaveamento_modalidade(mod)
        return mod, teams, chaveamento

    def test_intervencao_manual_admin_seleciona_times_nas_quartas(self):
        """
        Testa se a Comissão Organizadora pode intervir manualmente nas Quartas de Final,
        selecionando diretamente os times através da edição da partida, e se essa escolha
        manual fica fixada (definicao_manual=True) sem ser sobrescrita pelo algoritmo.
        """
        mod, teams, chaveamento = self._setup_modalidade_com_quartas("qman")
        quartas = list(chaveamento.partidas.filter(fase='QUARTAS_LOCAL').order_by('id'))
        self.assertTrue(len(quartas) >= 1)
        q1 = quartas[0]

        team_custom_1 = teams[0]
        team_custom_2 = teams[5]

        self.client.force_login(self.admin_user)
        url = reverse('chaveamento_partida_resultado', kwargs={'pk': q1.pk})

        response = self.client.post(url, {
            'has_team_selection': '1',
            'time_a': str(team_custom_1.pk),
            'time_b': str(team_custom_2.pk),
            'definicao_manual': '1',
            'placar_a': '',
            'placar_b': '',
            'wo_tipo': '',
        })
        self.assertEqual(response.status_code, 302)

        q1.refresh_from_db()
        self.assertTrue(q1.definicao_manual)
        self.assertEqual(q1.time_a, team_custom_1)
        self.assertEqual(q1.time_b, team_custom_2)
        self.assertIsNotNone(q1.jogo)
        self.assertEqual(q1.jogo.time_a, team_custom_1)
        self.assertEqual(q1.jogo.time_b, team_custom_2)

        # Chamar a rotina de preenchimento automático NÃO deve sobrescrever a escolha manual do admin
        from core.chaveamento_services import atualizar_classificados_e_preencher_mata_mata
        atualizar_classificados_e_preencher_mata_mata(chaveamento)

        q1.refresh_from_db()
        self.assertTrue(q1.definicao_manual)
        self.assertEqual(q1.time_a, team_custom_1)
        self.assertEqual(q1.time_b, team_custom_2)

    def test_intervencao_manual_desmarcar_restaura_preenchimento_automatico(self):
        """
        Testa se ao desmarcar 'Definição Manual' o sistema remove o bloqueio
        e restaura o cálculo automático dos confrontos com base nos classificados.
        """
        mod, teams, chaveamento = self._setup_modalidade_com_quartas("undoman")
        q1 = chaveamento.partidas.filter(fase='QUARTAS_LOCAL').first()
        q1.time_a = teams[0]
        q1.time_b = teams[1]
        q1.definicao_manual = True
        q1.save()

        self.client.force_login(self.admin_user)
        url = reverse('chaveamento_partida_resultado', kwargs={'pk': q1.pk})

        # Desmarca a definição manual (sem o checkbox definicao_manual enviado no POST)
        response = self.client.post(url, {
            'has_team_selection': '1',
            'time_a': str(teams[0].pk),
            'time_b': str(teams[1].pk),
            'placar_a': '',
            'placar_b': '',
        })
        self.assertEqual(response.status_code, 302)

        q1.refresh_from_db()
        self.assertFalse(q1.definicao_manual)

    def test_intervencao_manual_em_semifinais_protege_contra_avanco_automatico(self):
        """
        Testa se uma semifinal configurada manualmente pelo admin não é sobrescrita
        quando uma partida de quartas anterior for concluída e tentar avançar o vencedor.
        """
        mod, teams, chaveamento = self._setup_modalidade_com_quartas("semiman")
        q1 = chaveamento.partidas.filter(fase='QUARTAS_LOCAL').first()
        semi1 = chaveamento.partidas.filter(fase='SEMI_LOCAL').first()
        self.assertIsNotNone(semi1)

        # Fixa manualmente os times da semifinal
        semi1.time_a = teams[3]
        semi1.time_b = teams[4]
        semi1.definicao_manual = True
        semi1.save()

        # Configura e finaliza Q1 com vitória de outro time
        q1.time_a = teams[0]
        q1.time_b = teams[1]
        q1.proxima_partida = semi1
        q1.posicao_proxima_partida = 'A'
        q1.save()

        registrar_resultado_partida(q1, 5, 2)
        self.assertEqual(q1.vencedor, teams[0])

        # Semi 1 NÃO deve ter seu time_a alterado para o vencedor de Q1, pois está travada manualmente
        semi1.refresh_from_db()
        self.assertEqual(semi1.time_a, teams[3])
        self.assertEqual(semi1.time_b, teams[4])

    def test_chaveamento_admin_detail_view_exibe_seletores_de_time_e_badge_manual(self):
        """
        Testa se a página de gerenciamento do chaveamento renderiza o formulário de edição
        com os seletores de time para mata-mata e o badge de definição manual quando aplicável.
        """
        mod, teams, chaveamento = self._setup_modalidade_com_quartas("viewman")
        q1 = chaveamento.partidas.filter(fase='QUARTAS_LOCAL').first()
        q1.definicao_manual = True
        q1.save()

        self.client.force_login(self.admin_user)
        url = reverse('chaveamento_admin_detail', kwargs={'pk': mod.pk})
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertIn('delegacoes_modalidade', resp.context)
        self.assertContains(resp, 'name="time_a"')
        self.assertContains(resp, 'name="time_b"')
        self.assertContains(resp, 'Definição Manual')
        self.assertContains(resp, 'Manual')

    def test_is_jogo_rede_modalidades(self):
        """Testa a detecção automática de esportes de rede/sets."""
        volei = Modalidade.objects.create(nome="Voleibol Masculino", genero="M")
        tenis = Modalidade.objects.create(nome="Tênis de Mesa Feminino", genero="F")
        beach = Modalidade.objects.create(nome="Beach Tennis Misto", genero="X")
        futsal = Modalidade.objects.create(nome="Futsal Feminino", genero="F")
        basquete = Modalidade.objects.create(nome="Basquetebol Masculino", genero="M")

        self.assertTrue(volei.is_jogo_rede)
        self.assertTrue(tenis.is_jogo_rede)
        self.assertTrue(beach.is_jogo_rede)
        self.assertFalse(futsal.is_jogo_rede)
        self.assertFalse(basquete.is_jogo_rede)

    def test_salvar_e_remover_set_ajax(self):
        """Testa adição e remoção de sets via AJAX em uma partida."""
        mod = Modalidade.objects.create(nome="Vôlei de Praia Masculino", genero="M")
        chaveamento = ChaveamentoModalidade.objects.create(modalidade=mod)
        partida = PartidaChaveamento.objects.create(
            chaveamento=chaveamento,
            fase='FINAL',
            time_a=self.rep_user,
            time_b=self.admin_user
        )

        self.client.force_login(self.admin_user)
        url_salvar = reverse('chaveamento_set_salvar', kwargs={'pk': partida.pk})

        # 1. Tenta lançar empate no set (20x20) -> deve ser rejeitado
        resp = self.client.post(
            url_salvar,
            {'numero_set': 1, 'pontos_a': 20, 'pontos_b': 20},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data.get('success', True))

        # 2. Lança Set 1 (25x20 para time A)
        resp1 = self.client.post(
            url_salvar,
            {'numero_set': 1, 'pontos_a': 25, 'pontos_b': 20},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertEqual(data1['placar_a'], 1)
        self.assertEqual(data1['placar_b'], 0)
        self.assertEqual(data1['sets_resumo'], '25x20')

        # 3. Lança Set 2 (21x25 para time B)
        resp2 = self.client.post(
            url_salvar,
            {'numero_set': 2, 'pontos_a': 21, 'pontos_b': 25},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertEqual(data2['placar_a'], 1)
        self.assertEqual(data2['placar_b'], 1)
        self.assertEqual(data2['sets_resumo'], '25x20, 21x25')

        # 4. Lança Set 3 (15x11 para time A)
        resp3 = self.client.post(
            url_salvar,
            {'numero_set': 3, 'pontos_a': 15, 'pontos_b': 11},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp3.status_code, 200)
        data3 = resp3.json()
        self.assertEqual(data3['placar_a'], 2)
        self.assertEqual(data3['placar_b'], 1)
        self.assertEqual(data3['sets_resumo'], '25x20, 21x25, 15x11')
        set3_id = data3['set_id']

        # 5. Remove Set 3
        url_remover = reverse('chaveamento_set_remover', kwargs={'pk': set3_id})
        resp_rem = self.client.post(url_remover, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp_rem.status_code, 200)
        data_rem = resp_rem.json()
        self.assertEqual(data_rem['placar_a'], 1)
        self.assertEqual(data_rem['placar_b'], 1)
        self.assertEqual(data_rem['sets_resumo'], '25x20, 21x25')

    def test_partida_sets_computa_pontuacao_grupo_e_saldo_pontos(self):
        """Testa que os sets computam saldo de sets e saldo de pontos no grupo."""
        mod = Modalidade.objects.create(nome="Voleibol Feminino", genero="F")
        chaveamento = ChaveamentoModalidade.objects.create(modalidade=mod)
        grupo = GrupoChaveamento.objects.create(
            chaveamento=chaveamento,
            nome="Grupo Único",
            tipo='GERAL'
        )
        team1 = self._create_delegation("vol1@ufvjm.edu.br", "Vôlei Time 1", self.campus_dia)
        team2 = self._create_delegation("vol2@ufvjm.edu.br", "Vôlei Time 2", self.campus_dia)

        tg1 = TimeGrupo.objects.create(grupo=grupo, delegacao=team1)
        tg2 = TimeGrupo.objects.create(grupo=grupo, delegacao=team2)

        partida = PartidaChaveamento.objects.create(
            chaveamento=chaveamento,
            grupo=grupo,
            fase='GRUPOS',
            time_a=team1,
            time_b=team2
        )

        # Adiciona sets (2x0 para team1: 25x18, 25x20)
        SetPartida.objects.create(partida=partida, numero_set=1, pontos_a=25, pontos_b=18)
        SetPartida.objects.create(partida=partida, numero_set=2, pontos_a=25, pontos_b=20)

        # Finaliza partida via salvar_resultado_partida_view
        self.client.force_login(self.admin_user)
        url = reverse('chaveamento_partida_resultado', kwargs={'pk': partida.pk})
        resp = self.client.post(url, {
            'placar_a': 2,
            'placar_b': 0,
            'finalizada': 'on'
        })
        self.assertEqual(resp.status_code, 302)

        partida.refresh_from_db()
        self.assertTrue(partida.finalizada)
        self.assertEqual(partida.vencedor, team1)
        self.assertEqual(partida.placar_a, 2)
        self.assertEqual(partida.placar_b, 0)

        tg1.refresh_from_db()
        tg2.refresh_from_db()

        # tg1: 3 pts, 1 V, 0 E, 0 D, saldo sets +2 (gols_pro=2, gols_contra=0)
        self.assertEqual(tg1.pontos, 3)
        self.assertEqual(tg1.vitorias, 1)
        self.assertEqual(tg1.empates, 0)
        self.assertEqual(tg1.derrotas, 0)
        self.assertEqual(tg1.saldo_gols, 2)
        # Saldo de pontos nos sets: (25+25) - (18+20) = 50 - 38 = +12
        self.assertEqual(tg1.saldo_pontos_sets, 12)
        self.assertEqual(tg1.pontos_sets_pro, 50)
        self.assertEqual(tg1.pontos_sets_contra, 38)

        # tg2: 0 pts, 0 V, 0 E, 1 D, saldo sets -2
        self.assertEqual(tg2.pontos, 0)
        self.assertEqual(tg2.vitorias, 0)
        self.assertEqual(tg2.derrotas, 1)
        self.assertEqual(tg2.saldo_gols, -2)
        self.assertEqual(tg2.saldo_pontos_sets, -12)

    def test_desempate_grupo_por_saldo_pontos_sets(self):
        """Testa o desempate na fase de grupos quando dois times empatam em pts, vitorias e saldo de sets."""
        from core.chaveamento_services import ordenar_times_grupo

        mod = Modalidade.objects.create(nome="Tênis de Mesa Masculino", genero="M")
        chaveamento = ChaveamentoModalidade.objects.create(modalidade=mod)
        grupo = GrupoChaveamento.objects.create(
            chaveamento=chaveamento,
            nome="Grupo Desempate",
            tipo='GERAL'
        )
        team_a = self._create_delegation("tma@ufvjm.edu.br", "Tênis Time A", self.campus_dia)
        team_b = self._create_delegation("tmb@ufvjm.edu.br", "Tênis Time B", self.campus_dia)
        team_c = self._create_delegation("tmc@ufvjm.edu.br", "Tênis Time C", self.campus_dia)

        tg_a = TimeGrupo.objects.create(grupo=grupo, delegacao=team_a)
        tg_b = TimeGrupo.objects.create(grupo=grupo, delegacao=team_b)
        tg_c = TimeGrupo.objects.create(grupo=grupo, delegacao=team_c)

        # Partida 1: Team A vence Team C por 2x1 (sets: 11x4, 4x11, 11x5) -> sets +1, pontos: 26 pró, 20 contra = +6
        p1 = PartidaChaveamento.objects.create(
            chaveamento=chaveamento, grupo=grupo, fase='GRUPOS', time_a=team_a, time_b=team_c
        )
        SetPartida.objects.create(partida=p1, numero_set=1, pontos_a=11, pontos_b=4)
        SetPartida.objects.create(partida=p1, numero_set=2, pontos_a=4, pontos_b=11)
        SetPartida.objects.create(partida=p1, numero_set=3, pontos_a=11, pontos_b=5)
        self.client.force_login(self.admin_user)
        self.client.post(reverse('chaveamento_partida_resultado', kwargs={'pk': p1.pk}), {
            'placar_a': 2, 'placar_b': 1, 'finalizada': 'on'
        })

        # Partida 2: Team B vence Team C por 2x1 (sets: 11x9, 9x11, 11x9) -> sets +1, pontos: 31 pró, 29 contra = +2
        p2 = PartidaChaveamento.objects.create(
            chaveamento=chaveamento, grupo=grupo, fase='GRUPOS', time_a=team_b, time_b=team_c
        )
        SetPartida.objects.create(partida=p2, numero_set=1, pontos_a=11, pontos_b=9)
        SetPartida.objects.create(partida=p2, numero_set=2, pontos_a=9, pontos_b=11)
        SetPartida.objects.create(partida=p2, numero_set=3, pontos_a=11, pontos_b=9)
        self.client.post(reverse('chaveamento_partida_resultado', kwargs={'pk': p2.pk}), {
            'placar_a': 2, 'placar_b': 1, 'finalizada': 'on'
        })

        # Team A e Team B têm: 3 pontos, 1 vitória, 0 empates, 0 derrotas, saldo_sets = +1, sets_pro = 2.
        # Desempate deve ser saldo_pontos_sets: Team A (+6) > Team B (+2).
        ordenados = ordenar_times_grupo(grupo)
        self.assertEqual(ordenados[0].delegacao, team_a)
        self.assertEqual(ordenados[1].delegacao, team_b)
        self.assertEqual(ordenados[2].delegacao, team_c)

    def test_salvar_resultado_partida_com_link_pre_sumula(self):
        """Testa o salvamento e sincronização do link da pré-súmula via salvar_resultado_partida_view."""
        mod = Modalidade.objects.create(nome="Vôlei de Praia Masculino", genero="M")
        chaveamento = ChaveamentoModalidade.objects.create(modalidade=mod)
        team_a = self._create_delegation("vpa@ufvjm.edu.br", "Vôlei Time A", self.campus_dia)
        team_b = self._create_delegation("vpb@ufvjm.edu.br", "Vôlei Time B", self.campus_dia)

        partida = PartidaChaveamento.objects.create(
            chaveamento=chaveamento, fase='FINAL_LOCAL', time_a=team_a, time_b=team_b
        )
        from core.chaveamento_services import _sincronizar_jogo_partida
        _sincronizar_jogo_partida(partida)
        self.assertIsNotNone(partida.jogo)

        self.client.force_login(self.admin_user)
        url = reverse('chaveamento_partida_resultado', kwargs={'pk': partida.pk})

        # Salva resultado com link da pré-súmula (sem protocolo para testar auto-adição de https://)
        resp = self.client.post(url, {
            'placar_a': 2,
            'placar_b': 1,
            'link_pre_sumula': 'drive.google.com/file/d/12345/view'
        })
        self.assertEqual(resp.status_code, 302)

        partida.refresh_from_db()
        self.assertEqual(partida.link_pre_sumula, 'https://drive.google.com/file/d/12345/view')
        self.assertEqual(partida.placar_a, 2)
        self.assertEqual(partida.placar_b, 1)

        # Verifica sincronização com o modelo Jogo
        self.assertIsNotNone(partida.jogo)
        partida.jogo.refresh_from_db()
        self.assertEqual(partida.jogo.link_pre_sumula, 'https://drive.google.com/file/d/12345/view')
        self.assertEqual(partida.jogo.placar_time_a, 2)
        self.assertEqual(partida.jogo.placar_time_b, 1)

    def test_registrar_resultado_partida_com_link_pre_sumula_service(self):
        """Testa o service registrar_resultado_partida aceitando link_pre_sumula diretamente."""
        from core.chaveamento_services import registrar_resultado_partida, _sincronizar_jogo_partida

        mod = Modalidade.objects.create(nome="Handebol Feminino", genero="F")
        chaveamento = ChaveamentoModalidade.objects.create(modalidade=mod)
        team_a = self._create_delegation("hfa@ufvjm.edu.br", "Hand Time A", self.campus_dia)
        team_b = self._create_delegation("hfb@ufvjm.edu.br", "Hand Time B", self.campus_dia)

        partida = PartidaChaveamento.objects.create(
            chaveamento=chaveamento, fase='FINAL_GERAL', time_a=team_a, time_b=team_b
        )
        _sincronizar_jogo_partida(partida)

        link_teste = "https://docs.google.com/document/d/abcdef/edit"
        registrar_resultado_partida(partida, placar_a=20, placar_b=18, link_pre_sumula=link_teste)

        partida.refresh_from_db()
        self.assertEqual(partida.link_pre_sumula, link_teste)
        self.assertEqual(partida.jogo.link_pre_sumula, link_teste)
        self.assertTrue(partida.finalizada)
        self.assertEqual(partida.vencedor, team_a)

    def test_finalizar_jogo_com_link_pre_sumula(self):
        """Testa encerramento de jogo com adição do link de pré-súmula."""
        from core.chaveamento_services import _sincronizar_jogo_partida
        mod = Modalidade.objects.create(nome="Basquete Feminino", genero="F")
        chaveamento = ChaveamentoModalidade.objects.create(modalidade=mod)
        team_a = self._create_delegation("bfa@ufvjm.edu.br", "Basquete A", self.campus_dia)
        team_b = self._create_delegation("bfb@ufvjm.edu.br", "Basquete B", self.campus_dia)

        partida = PartidaChaveamento.objects.create(
            chaveamento=chaveamento, fase='FINAL_GERAL', time_a=team_a, time_b=team_b
        )
        _sincronizar_jogo_partida(partida)
        jogo = partida.jogo

        self.client.force_login(self.admin_user)
        url = reverse('jogo_finalizar', kwargs={'pk': jogo.pk})

        resp = self.client.post(url, {
            'link_pre_sumula': 'drive.google.com/presumula/basquete_final.pdf'
        })
        self.assertEqual(resp.status_code, 302)

        jogo.refresh_from_db()
        self.assertTrue(jogo.finalizado)
        self.assertEqual(jogo.link_pre_sumula, 'https://drive.google.com/presumula/basquete_final.pdf')

        partida.refresh_from_db()
        self.assertEqual(partida.link_pre_sumula, 'https://drive.google.com/presumula/basquete_final.pdf')

    def test_jogo_ajustar_horario_com_link_pre_sumula(self):
        """Testa ajuste de horário com atualização do link da pré-súmula."""
        from core.chaveamento_services import _sincronizar_jogo_partida
        mod = Modalidade.objects.create(nome="Futsal Feminino", genero="F")
        chaveamento = ChaveamentoModalidade.objects.create(modalidade=mod)
        team_a = self._create_delegation("ffa@ufvjm.edu.br", "Futsal A", self.campus_dia)
        team_b = self._create_delegation("ffb@ufvjm.edu.br", "Futsal B", self.campus_dia)

        partida = PartidaChaveamento.objects.create(
            chaveamento=chaveamento, fase='FINAL_GERAL', time_a=team_a, time_b=team_b
        )
        _sincronizar_jogo_partida(partida)
        jogo = partida.jogo

        self.client.force_login(self.admin_user)
        url = reverse('jogo_ajustar_horario', kwargs={'pk': jogo.pk})

        resp = self.client.post(url, {
            'data_jogo': '2026-10-15',
            'horario_jogo': '14:30',
            'link_pre_sumula': 'https://storage.ufvjm.edu.br/sumulas/futsal.pdf'
        })
        self.assertEqual(resp.status_code, 302)

        jogo.refresh_from_db()
        self.assertEqual(str(jogo.data_jogo), '2026-10-15')
        self.assertEqual(jogo.horario_jogo.strftime('%H:%M'), '14:30')
        self.assertEqual(jogo.link_pre_sumula, 'https://storage.ufvjm.edu.br/sumulas/futsal.pdf')

        partida.refresh_from_db()
        self.assertEqual(partida.link_pre_sumula, 'https://storage.ufvjm.edu.br/sumulas/futsal.pdf')

    def test_jogo_update_view_com_link_pre_sumula(self):
        """Testa edição completa de jogo com link_pre_sumula e sincronização com chaveamento."""
        from core.chaveamento_services import _sincronizar_jogo_partida
        mod = Modalidade.objects.create(nome="Xadrez Aberto", genero="M")
        chaveamento = ChaveamentoModalidade.objects.create(modalidade=mod)
        team_a = self._create_delegation("xaa@ufvjm.edu.br", "Xadrez A", self.campus_dia)
        team_b = self._create_delegation("xab@ufvjm.edu.br", "Xadrez B", self.campus_dia)

        partida = PartidaChaveamento.objects.create(
            chaveamento=chaveamento, fase='FINAL_GERAL', time_a=team_a, time_b=team_b
        )
        _sincronizar_jogo_partida(partida)
        jogo = partida.jogo

        self.client.force_login(self.admin_user)
        url = reverse('jogo_update', kwargs={'pk': jogo.pk})

        resp = self.client.post(url, {
            'modalidade': mod.pk,
            'data_jogo': '2026-10-20',
            'horario_jogo': '16:00',
            'time_a': team_a.pk,
            'time_b': team_b.pk,
            'local': 'Ginásio Campus I',
            'arbitro': 'Juiz Oficial',
            'placar_time_a': 1,
            'placar_time_b': 0,
            'link_pre_sumula': 'docs.google.com/spreadsheets/d/xadrez123',
            'finalizado': 'on'
        })
        self.assertEqual(resp.status_code, 302)

        jogo.refresh_from_db()
        self.assertEqual(jogo.link_pre_sumula, 'https://docs.google.com/spreadsheets/d/xadrez123')
        self.assertEqual(jogo.placar_time_a, 1)
        self.assertEqual(jogo.placar_time_b, 0)

        partida.refresh_from_db()
        self.assertEqual(partida.link_pre_sumula, 'https://docs.google.com/spreadsheets/d/xadrez123')
        self.assertEqual(partida.placar_a, 1)
        self.assertEqual(partida.placar_b, 0)

    def test_link_sumula_publica_renderizacao_publica(self):
        """Testa que a súmula adicionada é exibida publicamente em páginas abertas e anônimas."""
        mod = Modalidade.objects.create(nome="Natação Revezamento", genero="M")
        chaveamento = ChaveamentoModalidade.objects.create(modalidade=mod)
        team_a = self._create_delegation("nat_a@ufvjm.edu.br", "Natação A", self.campus_dia)
        team_b = self._create_delegation("nat_b@ufvjm.edu.br", "Natação B", self.campus_dia)

        partida = PartidaChaveamento.objects.create(
            chaveamento=chaveamento,
            fase='FINAL_GERAL',
            time_a=team_a,
            time_b=team_b,
            link_pre_sumula='https://docs.google.com/sumula-publica-teste'
        )
        from core.chaveamento_services import _sincronizar_jogo_partida
        _sincronizar_jogo_partida(partida)

        # Propriedades de fallback público
        self.assertEqual(partida.link_sumula_publica, 'https://docs.google.com/sumula-publica-teste')
        self.assertEqual(partida.jogo.link_sumula_publica, 'https://docs.google.com/sumula-publica-teste')

        # Usuário logado (representante/estudante) acessando chaveamento detalhado
        self.client.force_login(self.rep_user)
        resp = self.client.get(reverse('chaveamento_public_detail', kwargs={'pk': mod.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'https://docs.google.com/sumula-publica-teste')
        self.assertContains(resp, 'Acessar Súmula')

        # Usuário anônimo acessando link de compartilhamento aberto
        self.client.logout()
        resp_share = self.client.get(reverse('chaveamento_share', kwargs={'pk': mod.pk}))
        self.assertEqual(resp_share.status_code, 200)
        self.assertContains(resp_share, 'https://docs.google.com/sumula-publica-teste')

        # Usuário anônimo acessando lista cronológica pública de jogos
        resp_jogos = self.client.get(reverse('chaveamento_jogos_lista'))
        self.assertEqual(resp_jogos.status_code, 200)
        self.assertContains(resp_jogos, 'https://docs.google.com/sumula-publica-teste')

        # Teste para partida na Fase de Grupos
        grupo = GrupoChaveamento.objects.create(
            chaveamento=chaveamento,
            nome="Grupo Teste Súmula",
            tipo='GERAL'
        )
        partida_grupo = PartidaChaveamento.objects.create(
            chaveamento=chaveamento,
            grupo=grupo,
            fase='GRUPOS',
            time_a=team_a,
            time_b=team_b,
            link_pre_sumula='https://docs.google.com/sumula-grupo-publico'
        )
        _sincronizar_jogo_partida(partida_grupo)

        # Usuário anônimo acessando link de compartilhamento aberto deve ver a súmula da fase de grupos
        self.client.logout()
        resp_share_grupo = self.client.get(reverse('chaveamento_share', kwargs={'pk': mod.pk}))
        self.assertEqual(resp_share_grupo.status_code, 200)
        self.assertContains(resp_share_grupo, 'https://docs.google.com/sumula-grupo-publico')

        # Usuário de delegação acessando detalhe do chaveamento deve ver a súmula da fase de grupos
        self.client.force_login(self.rep_user)
        resp_pub_grupo = self.client.get(reverse('chaveamento_public_detail', kwargs={'pk': mod.pk}))
        self.assertEqual(resp_pub_grupo.status_code, 200)
        self.assertContains(resp_pub_grupo, 'https://docs.google.com/sumula-grupo-publico')


class ChaveamentoCustomizacaoFasesTestCase(ChaveamentoModuleTestCase):
    """
    Testes automatizados para a funcionalidade de customização de fases do chaveamento
    e intervenção manual no número de classificados por grupo.
    """
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)

    def test_salvar_vagas_grupo_e_atualizacao_classificados(self):
        """Testa a alteração manual de vagas de classificação e sua repercussão no grupo."""
        from core.chaveamento_services import salvar_vagas_grupo, atualizar_classificados_e_preencher_mata_mata

        mod = Modalidade.objects.create(nome="Basquete Teste Vagas", genero="M")
        chaveamento = ChaveamentoModalidade.objects.create(modalidade=mod)
        grupo = GrupoChaveamento.objects.create(chaveamento=chaveamento, nome="Grupo A", tipo="grupo_local", vagas_classificacao=2)

        t1 = self._create_delegation("basq1@ufvjm.edu.br", "Basq 1", self.campus_dia)
        t2 = self._create_delegation("basq2@ufvjm.edu.br", "Basq 2", self.campus_dia)
        t3 = self._create_delegation("basq3@ufvjm.edu.br", "Basq 3", self.campus_dia)

        tg1 = TimeGrupo.objects.create(grupo=grupo, delegacao=t1, pontos=9, jogos=2, vitorias=2)
        tg2 = TimeGrupo.objects.create(grupo=grupo, delegacao=t2, pontos=3, jogos=2, vitorias=1)
        tg3 = TimeGrupo.objects.create(grupo=grupo, delegacao=t3, pontos=0, jogos=2, derrotas=2)

        # Atualiza inicialmente com 2 vagas
        atualizar_classificados_e_preencher_mata_mata(chaveamento)
        tg1.refresh_from_db()
        tg2.refresh_from_db()
        tg3.refresh_from_db()
        self.assertTrue(tg1.classificado)
        self.assertTrue(tg2.classificado)
        self.assertFalse(tg3.classificado)

        # Altera para apenas 1 vaga passando
        salvar_vagas_grupo(grupo, 1)
        grupo.refresh_from_db()
        self.assertEqual(grupo.vagas_classificacao, 1)

        tg1.refresh_from_db()
        tg2.refresh_from_db()
        tg3.refresh_from_db()
        self.assertTrue(tg1.classificado)
        self.assertFalse(tg2.classificado)
        self.assertFalse(tg3.classificado)

    def test_salvar_vagas_grupo_view(self):
        """Testa o endpoint de salvar vagas de um grupo via POST."""
        mod = Modalidade.objects.create(nome="Handebol Teste View Vagas", genero="F")
        chaveamento = ChaveamentoModalidade.objects.create(modalidade=mod)
        grupo = GrupoChaveamento.objects.create(chaveamento=chaveamento, nome="Grupo 1", tipo="grupo_local", vagas_classificacao=2)

        url = reverse('chaveamento_grupo_salvar_vagas', kwargs={'pk': grupo.pk})
        resp = self.client.post(url, {'vagas_classificacao': 3})
        self.assertEqual(resp.status_code, 302)

        grupo.refresh_from_db()
        self.assertEqual(grupo.vagas_classificacao, 3)

    def test_remover_e_adicionar_fase_chaveamento(self):
        """Testa a remoção e reinclusão de fases com religamento da árvore de mata-mata."""
        from core.chaveamento_services import remover_fase_chaveamento, adicionar_fase_chaveamento

        mod = Modalidade.objects.create(nome="Futsal Fases Custom", genero="M")
        chaveamento = ChaveamentoModalidade.objects.create(modalidade=mod, datas_fases={'QUARTAS_LOCAL': '2026-10-10'})

        # Cria Quartas e Semis
        p_q1 = PartidaChaveamento.objects.create(chaveamento=chaveamento, fase='QUARTAS_LOCAL')
        p_q2 = PartidaChaveamento.objects.create(chaveamento=chaveamento, fase='QUARTAS_LOCAL')
        p_s1 = PartidaChaveamento.objects.create(chaveamento=chaveamento, fase='SEMI_LOCAL')
        p_f1 = PartidaChaveamento.objects.create(chaveamento=chaveamento, fase='FINAL_LOCAL')

        p_q1.proxima_partida = p_s1
        p_q1.save()
        p_s1.proxima_partida = p_f1
        p_s1.save()

        # Remove QUARTAS_LOCAL
        remover_fase_chaveamento(chaveamento, 'QUARTAS_LOCAL')

        self.assertFalse(PartidaChaveamento.objects.filter(chaveamento=chaveamento, fase='QUARTAS_LOCAL').exists())
        self.assertNotIn('QUARTAS_LOCAL', chaveamento.datas_fases)
        self.assertTrue(PartidaChaveamento.objects.filter(chaveamento=chaveamento, fase='SEMI_LOCAL').exists())

        # Reconexão deve manter p_s1 apontando para p_f1
        p_s1.refresh_from_db()
        self.assertEqual(p_s1.proxima_partida_id, p_f1.id)

        # Adiciona Quartas novamente
        adicionar_fase_chaveamento(chaveamento, 'QUARTAS_LOCAL', quantidade_partidas=2)
        novas_quartas = PartidaChaveamento.objects.filter(chaveamento=chaveamento, fase='QUARTAS_LOCAL')
        self.assertEqual(novas_quartas.count(), 2)

        # Verifica se as novas quartas foram ligadas à semi
        p_s1.refresh_from_db()
        for q in novas_quartas:
            self.assertEqual(q.proxima_partida_id, p_s1.id)

    def test_adicionar_e_remover_partida_avulsa(self):
        """Testa inclusão e exclusão de partidas avulsas."""
        from core.chaveamento_services import adicionar_partida_fase, remover_partida_chaveamento

        mod = Modalidade.objects.create(nome="Volei Partida Avulsa", genero="M")
        chaveamento = ChaveamentoModalidade.objects.create(modalidade=mod)

        partida = adicionar_partida_fase(chaveamento, 'SEMI_GERAL')
        self.assertIsNotNone(partida.pk)
        self.assertEqual(partida.fase, 'SEMI_GERAL')

        # Ao definir as equipes do confronto, o Jogo é criado
        t1 = self._create_delegation("v1@ufvjm.edu.br", "Volei 1", self.campus_dia)
        t2 = self._create_delegation("v2@ufvjm.edu.br", "Volei 2", self.campus_dia)
        partida.time_a = t1
        partida.time_b = t2
        partida.save()
        from core.chaveamento_services import _sincronizar_jogo_partida
        _sincronizar_jogo_partida(partida)

        self.assertIsNotNone(partida.jogo)
        self.assertFalse(partida.jogo.finalizado)

        # Remove partida e verifica exclusão segura da Partida e do Jogo
        partida_id = partida.pk
        jogo_id = partida.jogo.pk
        remover_partida_chaveamento(partida)

        self.assertFalse(PartidaChaveamento.objects.filter(pk=partida_id).exists())
        self.assertFalse(Jogo.objects.filter(pk=jogo_id).exists())

    def test_views_adicionar_e_remover_fase_e_partida(self):
        """Testa os endpoints HTTP de comissão para fases e partidas."""
        mod = Modalidade.objects.create(nome="Tenis Views Mod", genero="F")
        chaveamento = ChaveamentoModalidade.objects.create(modalidade=mod)

        # Adicionar fase via view
        resp = self.client.post(reverse('chaveamento_fase_adicionar', kwargs={'pk': chaveamento.pk}), {
            'fase_key': 'FINAL_GERAL',
            'quantidade_partidas': 1
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(PartidaChaveamento.objects.filter(chaveamento=chaveamento, fase='FINAL_GERAL').count(), 1)

        # Adicionar confronto avulso via view
        resp = self.client.post(reverse('chaveamento_partida_adicionar', kwargs={'pk': chaveamento.pk}), {
            'fase_key': 'FINAL_GERAL'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(PartidaChaveamento.objects.filter(chaveamento=chaveamento, fase='FINAL_GERAL').count(), 2)

        # Remover confronto avulso via view
        partida = PartidaChaveamento.objects.filter(chaveamento=chaveamento, fase='FINAL_GERAL').first()
        resp = self.client.post(reverse('chaveamento_partida_remover', kwargs={'pk': partida.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(PartidaChaveamento.objects.filter(chaveamento=chaveamento, fase='FINAL_GERAL').count(), 1)

        # Remover fase inteira via view
        resp = self.client.post(reverse('chaveamento_fase_remover', kwargs={'pk': chaveamento.pk}), {
            'fase_key': 'FINAL_GERAL'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(PartidaChaveamento.objects.filter(chaveamento=chaveamento, fase='FINAL_GERAL').count(), 0)

    def test_atualizar_classificados_com_fases_customizadas_sem_crashes(self):
        """Testa o preenchimento automático sem quebrar caso fases anteriores tenham sido removidas."""
        from core.chaveamento_services import atualizar_classificados_e_preencher_mata_mata

        mod = Modalidade.objects.create(nome="Xadrez Custom", genero="M")
        chaveamento = ChaveamentoModalidade.objects.create(modalidade=mod)

        # Grupo único de onde passa apenas 1 equipe
        grupo = GrupoChaveamento.objects.create(chaveamento=chaveamento, nome="Grupo Único", tipo="grupo_local", vagas_classificacao=1)
        t1 = self._create_delegation("xad1@ufvjm.edu.br", "Xad 1", self.campus_dia)
        t2 = self._create_delegation("xad2@ufvjm.edu.br", "Xad 2", self.campus_dia)
        TimeGrupo.objects.create(grupo=grupo, delegacao=t1, pontos=3, jogos=1, vitorias=1)
        TimeGrupo.objects.create(grupo=grupo, delegacao=t2, pontos=0, jogos=1, derrotas=1)

        # Mata-mata tem apenas FINAL_GERAL (sem Quartas ou Semis locais)
        final = PartidaChaveamento.objects.create(chaveamento=chaveamento, fase='FINAL_GERAL')

        # Atualização automática deve rodar perfeitamente sem IndexError
        atualizar_classificados_e_preencher_mata_mata(chaveamento)
        final.refresh_from_db()
        self.assertEqual(final.time_a_id, t1.id)
