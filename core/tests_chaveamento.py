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
        self.assertContains(res, "Chaveamentos Oficiais")
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






