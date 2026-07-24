import math
import random
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.contrib.auth import get_user_model
from core.models import (
    Modalidade, Campus, Jogo,
    ChaveamentoModalidade, GrupoChaveamento, TimeGrupo, PartidaChaveamento,
    InscricaoModalidade, Atleta
)

User = get_user_model()


def obter_resumo_chaveamentos_admin():
    """
    Retorna a lista de modalidades com estatísticas de delegações otimizada em apenas 3 queries (Zero N+1).
    """
    modalidades = list(
        Modalidade.objects.exclude(nome__icontains='atletismo')
        .select_related('chaveamento')
        .order_by('nome')
    )

    # 1. Busca todas as inscrições ativas e seus atletas em lote
    inscricoes_qs = list(
        InscricaoModalidade.objects.filter(inscricao__status='deferido')
        .select_related('inscricao__delegacao')
    )

    mod_inscricoes_map = {}
    for im in inscricoes_qs:
        if im.inscricao and im.inscricao.delegacao:
            mod_inscricoes_map.setdefault(im.modalidade_id, set()).add(im.inscricao.delegacao)

    # 2. Busca mapeamento em lote de delegação -> nome do campus
    atletas_campus_qs = Atleta.objects.filter(campus__isnull=False).select_related('campus').values('cadastrado_por_id', 'campus__nome')
    user_campus_name_map = {}
    for row in atletas_campus_qs:
        uid = row['cadastrado_por_id']
        if uid not in user_campus_name_map:
            user_campus_name_map[uid] = row['campus__nome'].lower()

    modalidades_info = []
    for m in modalidades:
        ch = getattr(m, 'chaveamento', None)
        delegacoes = list(mod_inscricoes_map.get(m.id, set()))

        # Fallback para inscrições sem filtro de status se estiver vazio
        if not delegacoes:
            raw_ims = InscricaoModalidade.objects.filter(modalidade=m).select_related('inscricao__delegacao')
            delegacoes = list(set(im.inscricao.delegacao for im in raw_ims if im.inscricao and im.inscricao.delegacao))

        mucuri_count = 0
        unai_count = 0
        janauba_count = 0
        diamantina_count = 0

        for d in delegacoes:
            c_nome = user_campus_name_map.get(d.id, '')
            if 'mucuri' in c_nome:
                mucuri_count += 1
            elif 'unaí' in c_nome or 'unai' in c_nome:
                unai_count += 1
            elif 'janaúba' in c_nome or 'janauba' in c_nome:
                janauba_count += 1
            else:
                diamantina_count += 1

        modalidades_info.append({
            'modalidade': m,
            'chaveamento': ch,
            'total_delegacoes': len(delegacoes),
            'mucuri_count': mucuri_count,
            'unai_count': unai_count,
            'janauba_count': janauba_count,
            'diamantina_count': diamantina_count,
        })

    return modalidades_info


def obter_resumo_chaveamentos_publico(delegacao_user):
    """
    Retorna a lista pública de modalidades e status de participação da delegação em 3 queries (Zero N+1).
    """
    modalidades = list(
        Modalidade.objects.exclude(nome__icontains='atletismo')
        .select_related('chaveamento')
        .order_by('nome')
    )

    meus_grupos_ch_ids = set()
    minhas_partidas_ch_ids = set()

    if delegacao_user:
        meus_grupos_ch_ids = set(
            TimeGrupo.objects.filter(delegacao=delegacao_user)
            .values_list('grupo__chaveamento_id', flat=True)
        )
        minhas_partidas_ch_ids = set(
            PartidaChaveamento.objects.filter(Q(time_a=delegacao_user) | Q(time_b=delegacao_user))
            .values_list('chaveamento_id', flat=True)
        )

    modalidades_info = []
    for m in modalidades:
        ch = getattr(m, 'chaveamento', None)
        minha_participacao = False
        if ch and (ch.id in meus_grupos_ch_ids or ch.id in minhas_partidas_ch_ids):
            minha_participacao = True

        modalidades_info.append({
            'modalidade': m,
            'chaveamento': ch,
            'minha_participacao': minha_participacao
        })

    return modalidades_info



def get_delegacao_campus(delegacao, modalidade=None):
    """
    Retorna o Campus ao qual a delegação pertence.
    Verifica primeiro os atletas vinculados à modalidade e fallback para atletas cadastrados.
    """
    if modalidade:
        im = InscricaoModalidade.objects.filter(
            inscricao__delegacao=delegacao,
            modalidade=modalidade
        ).first()
        if im and im.atletas.exists():
            campus_counts = {}
            for a in im.atletas.filter(campus__isnull=False):
                campus_counts[a.campus] = campus_counts.get(a.campus, 0) + 1
            if campus_counts:
                return max(campus_counts, key=campus_counts.get)

    # Fallback: primeiro atleta com campus cadastrado pela delegação
    atleta = Atleta.objects.filter(cadastrado_por=delegacao, campus__isnull=False).first()
    if atleta and atleta.campus:
        return atleta.campus

    # Fallback final: Campus Diamantina
    return Campus.objects.filter(nome__icontains='Diamantina').first() or Campus.objects.first()


def classificar_delegacoes_por_campus(modalidade):
    """
    Agrupa as delegações inscritas e deferidas na modalidade pelos 4 campi UFVJM:
    - Mucuri (externo)
    - Unaí (externo)
    - Janaúba (externo)
    - Diamantina (sede)
    """
    inscricoes_mod = InscricaoModalidade.objects.filter(
        modalidade=modalidade,
        inscricao__status='deferido'
    ).select_related('inscricao__delegacao')

    delegacoes = [im.inscricao.delegacao for im in inscricoes_mod if im.inscricao.delegacao]
    # Se não houver inscrições com status deferido, pega todas as inscrições para flexibilidade
    if not delegacoes:
        inscricoes_mod = InscricaoModalidade.objects.filter(
            modalidade=modalidade
        ).select_related('inscricao__delegacao')
        delegacoes = [im.inscricao.delegacao for im in inscricoes_mod if im.inscricao.delegacao]

    # Remove duplicatas
    delegacoes = list(set(delegacoes))

    campi_buckets = {
        'mucuri': [],
        'unai': [],
        'janauba': [],
        'diamantina': []
    }

    for del_user in delegacoes:
        c = get_delegacao_campus(del_user, modalidade)
        c_nome = c.nome.lower() if c else ''

        if 'mucuri' in c_nome:
            campi_buckets['mucuri'].append(del_user)
        elif 'unaí' in c_nome or 'unai' in c_nome:
            campi_buckets['unai'].append(del_user)
        elif 'janaúba' in c_nome or 'janauba' in c_nome:
            campi_buckets['janauba'].append(del_user)
        else:
            campi_buckets['diamantina'].append(del_user)

    return campi_buckets


@transaction.atomic
def gerar_chaveamento_modalidade(modalidade):
    """
    Gera o chaveamento completo de uma modalidade esportiva conforme as Diretrizes de Desenvolvimento.
    """
    # 1. Limpa chaveamento anterior se existir
    ChaveamentoModalidade.objects.filter(modalidade=modalidade).delete()

    chaveamento = ChaveamentoModalidade.objects.create(
        modalidade=modalidade,
        fase_atual='fase_grupos'
    )

    buckets = classificar_delegacoes_por_campus(modalidade)
    mucuri = buckets['mucuri']
    unai = buckets['unai']
    janauba = buckets['janauba']
    diamantina = buckets['diamantina']

    total_externos = mucuri + unai + janauba
    n_diamantina = len(diamantina)
    n_externos = len(total_externos)



    campus_mucuri = Campus.objects.filter(nome__icontains='Mucuri').first()
    campus_unai = Campus.objects.filter(nome__icontains='Unaí').first() or Campus.objects.filter(nome__icontains='Unai').first()
    campus_janauba = Campus.objects.filter(nome__icontains='Janaúba').first() or Campus.objects.filter(nome__icontains='Janauba').first()
    campus_diamantina = Campus.objects.filter(nome__icontains='Diamantina').first()

    vagas_ext_mucuri = 0
    vagas_ext_uj = 0
    classificados_externos_iniciais = []

    # -------------------------------------------------------------
    # 2. Regras dos Campi Externos (Máximo 2 vagas na Fase Geral)
    # -------------------------------------------------------------

    # Mucuri: Se houver 2 delegações inscritas, competem entre si por 1 vaga na semifinal geral.
    # Se houver 1, avança direto.
    if len(mucuri) >= 2:
        grupo_mucuri = GrupoChaveamento.objects.create(
            chaveamento=chaveamento,
            nome="Eliminatória Campus Mucuri",
            campus=campus_mucuri,
            tipo="eliminatoria_ext",
            vagas_classificacao=1
        )
        for team in mucuri:
            TimeGrupo.objects.create(grupo=grupo_mucuri, delegacao=team)
        # Gerar partidas todos contra todos ou confronto direto
        _gerar_partidas_grupo(grupo_mucuri, fase_nome='EXTERNO_ELIMINATORIA')
        vagas_ext_mucuri = 1
        classificados_externos_iniciais.append(None)
    elif len(mucuri) == 1:
        grupo_mucuri = GrupoChaveamento.objects.create(
            chaveamento=chaveamento,
            nome="Classificado Campus Mucuri",
            campus=campus_mucuri,
            tipo="eliminatoria_ext",
            vagas_classificacao=1
        )
        TimeGrupo.objects.create(grupo=grupo_mucuri, delegacao=mucuri[0], classificado=True)
        vagas_ext_mucuri = 1
        classificados_externos_iniciais.append(mucuri[0])

    # Unaí e Janaúba: Se ambos tiverem time inscrito, enfrentam-se por 1 vaga na semifinal geral.
    # Se apenas um deles se inscrever, este avança direto para a semifinal geral.
    teams_uj = unai + janauba
    if len(unai) > 0 and len(janauba) > 0:
        grupo_uj = GrupoChaveamento.objects.create(
            chaveamento=chaveamento,
            nome="Eliminatória Unaí vs Janaúba",
            campus=campus_unai or campus_janauba,
            tipo="eliminatoria_ext",
            vagas_classificacao=1
        )
        for team in teams_uj:
            TimeGrupo.objects.create(grupo=grupo_uj, delegacao=team)
        _gerar_partidas_grupo(grupo_uj, fase_nome='EXTERNO_ELIMINATORIA')
        vagas_ext_uj = 1
        classificados_externos_iniciais.append(None)
    elif len(teams_uj) > 0:
        grupo_uj = GrupoChaveamento.objects.create(
            chaveamento=chaveamento,
            nome=f"Classificado Campus {'Unaí' if len(unai)>0 else 'Janaúba'}",
            campus=campus_unai if len(unai)>0 else campus_janauba,
            tipo="eliminatoria_ext",
            vagas_classificacao=1
        )
        for team in teams_uj:
            TimeGrupo.objects.create(grupo=grupo_uj, delegacao=team, classificado=True)
        vagas_ext_uj = 1
        classificados_externos_iniciais.append(teams_uj[0])

    total_vagas_externas = vagas_ext_mucuri + vagas_ext_uj
    chaveamento.vagas_externas = total_vagas_externas
    chaveamento.save()

    # -------------------------------------------------------------
    # 3. Regras do Campus Sede (Diamantina)
    # Formato Híbrido (Grupos + Mata-mata)
    # -------------------------------------------------------------
    n_diamantina = len(diamantina)
    if n_diamantina > 1:
        _construir_fase_grupos_diamantina(chaveamento, diamantina, campus_diamantina)

    # -------------------------------------------------------------
    # 4. Estrutura Completa de Mata-Mata Gerada Imediatamente
    # -------------------------------------------------------------
    if n_diamantina == 1:
        classificados_local = [diamantina[0]]
    else:
        num_vagas_local = sum(g.vagas_classificacao for g in chaveamento.grupos.filter(tipo='grupo_local'))
        if num_vagas_local == 0 and n_diamantina > 0:
            num_vagas_local = n_diamantina
        if num_vagas_local == 0:
            num_vagas_local = 2
        classificados_local = [None] * num_vagas_local

    _construir_mata_mata_diamantina(chaveamento, classificados_local, classificados_externos_iniciais)

    return chaveamento


def _construir_fase_grupos_diamantina(chaveamento, teams, campus_diamantina):
    """
    Constrói a fase de grupos para Diamantina conforme diretrizes:
    - Quando a quantidade for ímpar, cria grupos de 4 (passam 3) e/ou 3 (passam 2)
      garantindo soma PAR de classificados.
    """
    n = len(teams)
    # Randomiza times para distribuição justa
    shuffled_teams = list(teams)
    random.shuffle(shuffled_teams)

    # Determina a divisão dos grupos
    # Desejamos grupos de tamanho 3 ou 4.
    grupos_sizes = []

    if n <= 2:
        grupos_sizes = [n]
    elif n == 3:
        grupos_sizes = [3]  # passa 2 (par!)
    elif n == 4:
        grupos_sizes = [4]  # passa 3 ou 4; se par directo mata-mata/grupo único
    elif n == 5:
        grupos_sizes = [3, 2] # 3 (passam 2) + 2 (passam 2) = 4 classificados
    elif n == 6:
        grupos_sizes = [3, 3] # 3 (passam 2) + 3 (passam 2) = 4 classificados
    elif n == 7:
        grupos_sizes = [4, 3] # 4 (passam 2) + 3 (passam 2) = 4 classificados
    elif n == 8:
        grupos_sizes = [4, 4] # 4 (passam 3 cada) = 6 classificados -> adjust to pass 4 or 6 (par)
    elif n == 9:
        grupos_sizes = [3, 3, 3] # 3 (passam 2 cada) = 6 classificados (par!)
    elif n == 11:
        grupos_sizes = [4, 4, 3] # 4 (passam 3) + 4 (passam 3) + 3 (passam 2) = 8 classificados (par!)
    else:
        # Algoritmo genérico para N > 11:
        # Tenta dividir em grupos de 4 e 3
        num_g4 = n // 4
        rem = n % 4
        if rem == 1:
            num_g4 -= 1
            num_g3 = 3
        elif rem == 2:
            num_g4 -= 1
            num_g3 = 2
        elif rem == 3:
            num_g3 = 1
        else:
            num_g3 = 0

        grupos_sizes = [4] * num_g4 + [3] * num_g3

    idx = 0
    letra_code = ord('A')

    for size in grupos_sizes:
        group_name = f"Grupo {chr(letra_code)}"
        letra_code += 1

        # Regra de classificação:
        # Grupos de 4 times: passam 3
        # Grupos de 3 times: passam 2
        # Grupos de 2 times: passam 2
        if size == 4:
            vagas = 3
        elif size == 3:
            vagas = 2
        elif size == 2:
            vagas = 2
        else:
            vagas = min(size, 4)

        grupo = GrupoChaveamento.objects.create(
            chaveamento=chaveamento,
            nome=group_name,
            campus=campus_diamantina,
            tipo="grupo_local",
            vagas_classificacao=vagas
        )

        group_teams = shuffled_teams[idx:idx+size]
        idx += size

        for team in group_teams:
            TimeGrupo.objects.create(grupo=grupo, delegacao=team)

        _gerar_partidas_grupo(grupo, fase_nome='GRUPO_LOCAL')


def _gerar_partidas_grupo(grupo, fase_nome='GRUPO_LOCAL'):
    """
    Gera as partidas 'todos contra todos' para um grupo.
    """
    times = list(grupo.times.all())
    n = len(times)
    if n < 2:
        return

    rodada = 1
    for i in range(n):
        for j in range(i + 1, n):
            team_a = times[i].delegacao
            team_b = times[j].delegacao

            # Cria a partida no chaveamento
            partida = PartidaChaveamento.objects.create(
                chaveamento=grupo.chaveamento,
                fase=fase_nome,
                grupo=grupo,
                rodada=rodada,
                time_a=team_a,
                time_b=team_b
            )

            # Também cria/sincroniza o Jogo no sistema geral
            hoje = timezone.localdate()
            jogo = Jogo.objects.create(
                modalidade=grupo.chaveamento.modalidade,
                data_jogo=hoje,
                time_a=team_a,
                time_b=team_b,
                local="Quadra Principal (Diamantina)" if grupo.tipo == "grupo_local" else "Campus de Origem"
            )
            partida.jogo = jogo
            partida.save()

            rodada += 1


def atualizar_tabela_grupo(grupo):
    """
    Recalcula a tabela de classificação do grupo com base nas partidas finalizadas.
    """
    partidas = grupo.partidas.filter(finalizada=True)
    stats = {tg.delegacao_id: {
        'pontos': 0, 'jogos': 0, 'vitorias': 0, 'empates': 0, 'derrotas': 0,
        'gols_pro': 0, 'gols_contra': 0, 'saldo_gols': 0
    } for tg in grupo.times.all()}

    for p in partidas:
        if p.time_a_id not in stats or p.time_b_id not in stats:
            continue
        if p.placar_a is None or p.placar_b is None:
            continue

        st_a = stats[p.time_a_id]
        st_b = stats[p.time_b_id]

        st_a['jogos'] += 1
        st_b['jogos'] += 1

        st_a['gols_pro'] += p.placar_a
        st_a['gols_contra'] += p.placar_b
        st_a['saldo_gols'] = st_a['gols_pro'] - st_a['gols_contra']

        st_b['gols_pro'] += p.placar_b
        st_b['gols_contra'] += p.placar_a
        st_b['saldo_gols'] = st_b['gols_pro'] - st_b['gols_contra']

        if p.placar_a > p.placar_b:
            st_a['pontos'] += 3
            st_a['vitorias'] += 1
            st_b['derrotas'] += 1
        elif p.placar_b > p.placar_a:
            st_b['pontos'] += 3
            st_b['vitorias'] += 1
            st_a['derrotas'] += 1
        else:
            st_a['pontos'] += 1
            st_b['pontos'] += 1
            st_a['empates'] += 1
            st_b['empates'] += 1

    for tg in grupo.times.all():
        st = stats.get(tg.delegacao_id)
        if st:
            tg.pontos = st['pontos']
            tg.jogos = st['jogos']
            tg.vitorias = st['vitorias']
            tg.empates = st['empates']
            tg.derrotas = st['derrotas']
            tg.gols_pro = st['gols_pro']
            tg.gols_contra = st['gols_contra']
            tg.saldo_gols = st['saldo_gols']
            tg.save()


@transaction.atomic
def registrar_resultado_partida(partida, placar_a, placar_b):
    """
    Registra o resultado de uma partida, atualiza tabelas de grupo e avança vencedores na árvore de mata-mata.
    """
    partida.placar_a = placar_a
    partida.placar_b = placar_b
    partida.finalizada = True

    if placar_a > placar_b:
        partida.vencedor = partida.time_a
        partida.perdedor = partida.time_b
    elif placar_b > placar_a:
        partida.vencedor = partida.time_b
        partida.perdedor = partida.time_a
    else:
        # Se for partida de mata-mata com empate, atribui vencedor ao time A por padrão para evitar travamento
        partida.vencedor = partida.time_a
        partida.perdedor = partida.time_b

    partida.save()

    # Sincroniza modelo Jogo se existir
    if partida.jogo:
        jogo = partida.jogo
        jogo.placar_time_a = placar_a
        jogo.placar_time_b = placar_b
        jogo.finalizado = True
        jogo.save()

    # Se for partida de grupo, atualiza a tabela do grupo e avança classificados
    if partida.grupo:
        atualizar_tabela_grupo(partida.grupo)
        atualizar_classificados_e_preencher_mata_mata(partida.chaveamento)

    # Avança vencedor para a próxima partida se configurado
    if partida.proxima_partida and partida.vencedor:
        prox = partida.proxima_partida
        if partida.posicao_proxima_partida == 'A':
            prox.time_a = partida.vencedor
        elif partida.posicao_proxima_partida == 'B':
            prox.time_b = partida.vencedor
        prox.save()
        _sincronizar_jogo_partida(prox, "Mata-Mata")

    # Avança perdedor para partida de perdedor (Chave Bronze / 3º lugar) se configurado
    if partida.partida_perdedor_destino and partida.perdedor:
        dest = partida.partida_perdedor_destino
        if partida.posicao_perdedor_destino == 'A':
            dest.time_a = partida.perdedor
        elif partida.posicao_perdedor_destino == 'B':
            dest.time_b = partida.perdedor
        dest.save()
        _sincronizar_jogo_partida(dest, "Chave Bronze / 3º Lugar")

    return partida


@transaction.atomic
def atualizar_classificados_e_preencher_mata_mata(chaveamento):
    """
    Atualiza os classificados dos grupos SOMENTE quando todas as partidas do grupo forem concluídas (ou se não houver partidas no grupo).
    Preenche dinamicamente as vagas do Mata-Mata pré-existente.
    """
    for g in chaveamento.grupos.all():
        atualizar_tabela_grupo(g)

    classificados_diamantina = []
    classificados_externos = []

    for g in chaveamento.grupos.all():
        has_matches = g.partidas.exists()
        grupo_concluido = (not g.partidas.filter(finalizada=False).exists()) if has_matches else True

        times_ordenados = list(g.times.order_by('-pontos', '-vitorias', '-saldo_gols', '-gols_pro'))
        vagas = g.vagas_classificacao

        for idx, tg in enumerate(times_ordenados):
            # Só marca como classificado se o grupo estver 100% concluído (ou sem partidas pendentes)
            if grupo_concluido and idx < vagas:
                tg.classificado = True
                if g.tipo == 'grupo_local':
                    classificados_diamantina.append(tg.delegacao)
                else:
                    classificados_externos.append(tg.delegacao)
            else:
                tg.classificado = False
            tg.save()

    classificados_diamantina = list(dict.fromkeys(classificados_diamantina))
    classificados_externos = list(dict.fromkeys(classificados_externos))

    quartas = list(chaveamento.partidas.filter(fase='QUARTAS_LOCAL').order_by('id'))
    semis_local = list(chaveamento.partidas.filter(fase='SEMI_LOCAL').order_by('id'))
    semis_geral = list(chaveamento.partidas.filter(fase='SEMI_GERAL').order_by('id'))
    final_local = chaveamento.partidas.filter(fase='FINAL_LOCAL').first()

    if quartas:
        pairings = [(0, 7), (3, 4), (1, 6), (2, 5)]
        for i, q in enumerate(quartas):
            idx_a, idx_b = pairings[i]
            q.time_a = classificados_diamantina[idx_a] if idx_a < len(classificados_diamantina) else None
            q.time_b = classificados_diamantina[idx_b] if idx_b < len(classificados_diamantina) else None
            q.save()
            _sincronizar_jogo_partida(q, f"Quartas {i+1} (Diamantina)")
    elif semis_local:
        if len(semis_local) >= 1:
            semis_local[0].time_a = classificados_diamantina[0] if len(classificados_diamantina) >= 1 else None
            semis_local[0].time_b = classificados_diamantina[3] if len(classificados_diamantina) >= 4 else None
            semis_local[0].save()
            _sincronizar_jogo_partida(semis_local[0], "Semifinal 1 (Diamantina)")
        if len(semis_local) >= 2:
            semis_local[1].time_a = classificados_diamantina[1] if len(classificados_diamantina) >= 2 else None
            semis_local[1].time_b = classificados_diamantina[2] if len(classificados_diamantina) >= 3 else None
            semis_local[1].save()
            _sincronizar_jogo_partida(semis_local[1], "Semifinal 2 (Diamantina)")
    elif final_local and not quartas and not semis_local:
        final_local.time_a = classificados_diamantina[0] if len(classificados_diamantina) >= 1 else None
        final_local.time_b = classificados_diamantina[1] if len(classificados_diamantina) >= 2 else None
        final_local.save()
        _sincronizar_jogo_partida(final_local, "Final de Diamantina")

    if semis_geral:
        if len(semis_geral) >= 1:
            semis_geral[0].time_b = classificados_externos[0] if len(classificados_externos) >= 1 else None
            semis_geral[0].save()
            _sincronizar_jogo_partida(semis_geral[0], "Semifinal Geral 1")
        if len(semis_geral) >= 2:
            semis_geral[1].time_b = classificados_externos[1] if len(classificados_externos) >= 2 else None
            semis_geral[1].save()
            _sincronizar_jogo_partida(semis_geral[1], "Semifinal Geral 2")


def encerrar_fase_grupos_e_gerar_mata_mata(chaveamento):
    atualizar_classificados_e_preencher_mata_mata(chaveamento)


def _construir_mata_mata_diamantina(chaveamento, classificados_local, classificados_externos):
    """
    Constrói a estrutura do Mata-Mata de Diamantina e prepara as Semifinais Gerais.
    """
    n_local = len(classificados_local)
    vagas_ext = chaveamento.vagas_externas

    if n_local == 0:
        return

    # Caso Excepcional: 1 classificado local + 1 vaga externa -> Vai DIRETO para a Grande Final Geral
    if n_local == 1 and vagas_ext == 1:
        ext_team = classificados_externos[0] if classificados_externos else None
        final_geral = PartidaChaveamento.objects.create(
            chaveamento=chaveamento,
            fase='FINAL_GERAL',
            time_a=classificados_local[0],
            time_b=ext_team
        )
        _sincronizar_jogo_partida(final_geral, "Grande Final Geral")

        # Conecta eliminatórias externas à Final Geral (posição B) se houverem partidas eliminatórias
        partidas_ext = PartidaChaveamento.objects.filter(
            chaveamento=chaveamento,
            fase='EXTERNO_ELIMINATORIA'
        )
        for p_ext in partidas_ext:
            p_ext.proxima_partida = final_geral
            p_ext.posicao_proxima_partida = 'B'
            p_ext.save()

        chaveamento.fase_atual = 'fase_geral'
        chaveamento.save()
        return

    # Caso 1: 2 classificados locais -> Já são o Campeão e Vice de Diamantina
    if n_local == 2:
        final_local = PartidaChaveamento.objects.create(
            chaveamento=chaveamento,
            fase='FINAL_LOCAL',
            time_a=classificados_local[0],
            time_b=classificados_local[1]
        )
        _sincronizar_jogo_partida(final_local, "Final de Diamantina")
        _montar_fase_geral(chaveamento, final_local, None, classificados_externos)

    # Caso 2: 4 classificados locais -> Semifinais de Diamantina
    elif n_local <= 4:
        # Garante 4 elementos com None se necessário
        t = classificados_local + [None] * (4 - len(classificados_local))

        disputa_3_local = PartidaChaveamento.objects.create(
            chaveamento=chaveamento,
            fase='DISPUTA_3_LOCAL'
        )
        _sincronizar_jogo_partida(disputa_3_local, "Disputa 3º Lugar (Diamantina)")

        final_local = PartidaChaveamento.objects.create(
            chaveamento=chaveamento,
            fase='FINAL_LOCAL'
        )
        _sincronizar_jogo_partida(final_local, "Final Local (Diamantina)")

        semi1_local = PartidaChaveamento.objects.create(
            chaveamento=chaveamento,
            fase='SEMI_LOCAL',
            time_a=t[0],
            time_b=t[3],
            proxima_partida=final_local,
            posicao_proxima_partida='A',
            partida_perdedor_destino=disputa_3_local,
            posicao_perdedor_destino='A'
        )
        _sincronizar_jogo_partida(semi1_local, "Semifinal 1 (Diamantina)")

        semi2_local = PartidaChaveamento.objects.create(
            chaveamento=chaveamento,
            fase='SEMI_LOCAL',
            time_a=t[1],
            time_b=t[2],
            proxima_partida=final_local,
            posicao_proxima_partida='B',
            partida_perdedor_destino=disputa_3_local,
            posicao_perdedor_destino='B'
        )
        _sincronizar_jogo_partida(semi2_local, "Semifinal 2 (Diamantina)")

        _montar_fase_geral(chaveamento, final_local, disputa_3_local, classificados_externos)

    # Caso 3: 6 ou 8 classificados locais -> Quartas de Final de Diamantina
    else:
        t = classificados_local + [None] * (8 - len(classificados_local))

        disputa_3_local = PartidaChaveamento.objects.create(
            chaveamento=chaveamento,
            fase='DISPUTA_3_LOCAL'
        )
        _sincronizar_jogo_partida(disputa_3_local, "Disputa 3º Lugar (Diamantina)")

        final_local = PartidaChaveamento.objects.create(
            chaveamento=chaveamento,
            fase='FINAL_LOCAL'
        )
        _sincronizar_jogo_partida(final_local, "Final Local (Diamantina)")

        semi1_local = PartidaChaveamento.objects.create(
            chaveamento=chaveamento,
            fase='SEMI_LOCAL',
            proxima_partida=final_local,
            posicao_proxima_partida='A',
            partida_perdedor_destino=disputa_3_local,
            posicao_perdedor_destino='A'
        )
        _sincronizar_jogo_partida(semi1_local, "Semifinal 1 (Diamantina)")

        semi2_local = PartidaChaveamento.objects.create(
            chaveamento=chaveamento,
            fase='SEMI_LOCAL',
            proxima_partida=final_local,
            posicao_proxima_partida='B',
            partida_perdedor_destino=disputa_3_local,
            posicao_perdedor_destino='B'
        )
        _sincronizar_jogo_partida(semi2_local, "Semifinal 2 (Diamantina)")

        # 4 Quartas de Final
        q1 = PartidaChaveamento.objects.create(
            chaveamento=chaveamento, fase='QUARTAS_LOCAL', time_a=t[0], time_b=t[7],
            proxima_partida=semi1_local, posicao_proxima_partida='A'
        )
        _sincronizar_jogo_partida(q1, "Quartas 1 (Diamantina)")

        q2 = PartidaChaveamento.objects.create(
            chaveamento=chaveamento, fase='QUARTAS_LOCAL', time_a=t[3], time_b=t[4],
            proxima_partida=semi1_local, posicao_proxima_partida='B'
        )
        _sincronizar_jogo_partida(q2, "Quartas 2 (Diamantina)")

        q3 = PartidaChaveamento.objects.create(
            chaveamento=chaveamento, fase='QUARTAS_LOCAL', time_a=t[1], time_b=t[6],
            proxima_partida=semi2_local, posicao_proxima_partida='A'
        )
        _sincronizar_jogo_partida(q3, "Quartas 3 (Diamantina)")

        q4 = PartidaChaveamento.objects.create(
            chaveamento=chaveamento, fase='QUARTAS_LOCAL', time_a=t[2], time_b=t[5],
            proxima_partida=semi2_local, posicao_proxima_partida='B'
        )
        _sincronizar_jogo_partida(q4, "Quartas 4 (Diamantina)")

        _montar_fase_geral(chaveamento, final_local, disputa_3_local, classificados_externos)


def _montar_fase_geral(chaveamento, final_local, disputa_3_local, classificados_externos):
    """
    Integra os campeões de Diamantina com as vagas externas nas Semifinais Gerais e Chave Bronze.
    """
    vagas_ext = chaveamento.vagas_externas
    ext1 = classificados_externos[0] if len(classificados_externos) > 0 else None
    ext2 = classificados_externos[1] if len(classificados_externos) > 1 else None

    # Se não houver vagas externas (0 vagas), o chaveamento local de Diamantina é o chaveamento geral!
    if vagas_ext == 0:
        return

    # Chave Bronze (3º e 4º Geral): Reúne perdedores das semifinais locais e gerais
    chave_bronze = PartidaChaveamento.objects.create(
        chaveamento=chaveamento,
        fase='BRONZE'
    )
    _sincronizar_jogo_partida(chave_bronze, "Disputa de 3º Lugar (Chave Bronze Geral)")

    final_geral = PartidaChaveamento.objects.create(
        chaveamento=chaveamento,
        fase='FINAL_GERAL'
    )
    _sincronizar_jogo_partida(final_geral, "Grande Final Geral")

    semi_geral_1 = PartidaChaveamento.objects.create(
        chaveamento=chaveamento,
        fase='SEMI_GERAL',
        time_b=ext1,
        proxima_partida=final_geral,
        posicao_proxima_partida='A',
        partida_perdedor_destino=chave_bronze,
        posicao_perdedor_destino='A'
    )
    _sincronizar_jogo_partida(semi_geral_1, "Semifinal Geral 1")

    semi_geral_2 = PartidaChaveamento.objects.create(
        chaveamento=chaveamento,
        fase='SEMI_GERAL',
        time_b=ext2 if vagas_ext == 2 else None,
        proxima_partida=final_geral,
        posicao_proxima_partida='B',
        partida_perdedor_destino=chave_bronze,
        posicao_perdedor_destino='B'
    )
    _sincronizar_jogo_partida(semi_geral_2, "Semifinal Geral 2")

    # Conecta o Campeão de Diamantina -> Semi Geral 1 (time_a)
    if final_local:
        final_local.proxima_partida = semi_geral_1
        final_local.posicao_proxima_partida = 'A'
        final_local.save()

    # Se 2 vagas externas -> Vice de Diamantina vai para Semi Geral 2 (time_a)
    if vagas_ext == 2 and final_local:
        final_local.partida_perdedor_destino = semi_geral_2
        final_local.posicao_perdedor_destino = 'A'
        final_local.save()

    # Se 1 vaga externa -> Diamantina envia 3 times (Campeão, Vice e 3º Colocado)
    elif vagas_ext == 1:
        if final_local:
            final_local.partida_perdedor_destino = semi_geral_2
            final_local.posicao_perdedor_destino = 'A'
            final_local.save()
        if disputa_3_local:
            disputa_3_local.proxima_partida = semi_geral_2
            disputa_3_local.posicao_proxima_partida = 'B'
            disputa_3_local.save()


def _sincronizar_jogo_partida(partida, descricao_local="Quadra Principal"):
    """
    Garante que uma PartidaChaveamento tenha um Jogo correspondente no sistema.
    """
    if not partida.jogo and (partida.time_a or partida.time_b):
        hoje = timezone.localdate()
        dummy_b = partida.time_b or partida.time_a
        dummy_a = partida.time_a or partida.time_b
        if dummy_a and dummy_b:
            jogo = Jogo.objects.create(
                modalidade=partida.chaveamento.modalidade,
                data_jogo=hoje,
                time_a=dummy_a,
                time_b=dummy_b,
                local=descricao_local
            )
            partida.jogo = jogo
            partida.save()
