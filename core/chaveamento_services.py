import math
import random
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.contrib.auth import get_user_model
from core.models import (
    Modalidade, Campus, Jogo,
    ChaveamentoModalidade, GrupoChaveamento, TimeGrupo, PartidaChaveamento,
    InscricaoModalidade, Atleta, CartaoPartida
)

User = get_user_model()


def _is_queimada(modalidade):
    if not modalidade:
        return False
    nome = (modalidade.nome or '').lower()
    return 'queimada' in nome or 'dodgeball' in nome


def _is_formato_3_grupos_melhor_segundo(modalidade):
    if not modalidade:
        return False
    if _is_queimada(modalidade):
        return True
    formato = getattr(modalidade, 'formato_chaveamento', None) or 'padrao'
    return formato == 'formato_3_grupos_melhor_segundo'


def _calcular_melhor_segundo_colocado(segundos_colocados, modalidade):
    """
    Calcula o melhor 2º colocado geral entre os 3 grupos com base nas regras exclusivas deste formato:
    1. maior número de vitórias;
    2. maior saldo de jogadores (saldo_gols);
    3. maior número de jogadores adversários eliminados (gols_pro);
    4. menor número de jogadores da própria equipe eliminados (gols_contra);
    5. menor número de penalidades (cartões);
    6. sorteio.
    """
    if not segundos_colocados:
        return None

    ranking = []
    for tg in segundos_colocados:
        penalidades = CartaoPartida.objects.filter(
            modalidade=modalidade,
            delegacao=tg.delegacao,
            partida__fase='GRUPO_LOCAL'
        ).count()

        sorteio_val = random.random()
        ranking.append((
            tg,
            -tg.vitorias,
            -tg.saldo_gols,
            -tg.gols_pro,
            tg.gols_contra,
            penalidades,
            sorteio_val
        ))

    ranking.sort(key=lambda item: (item[1], item[2], item[3], item[4], item[5], item[6]))
    return ranking[0][0]


def _emparelhar_semifinais_3_grupos(vencedores_grupos, best_segundo, partidas_grupo):
    """
    Define os confrontos de Semifinal para o formato 3 grupos:
    - Evita repetir confrontos da fase de grupos;
    - O melhor 2º enfrenta um vencedor de grupo diferente do seu;
    - Os outros dois vencedores de grupo se enfrentam;
    - Somente quando não existir outra combinação válida será permitido repetir confronto da fase de grupos.
    """
    confrontos_grupo_set = set()
    for p in partidas_grupo:
        if p.time_a_id and p.time_b_id:
            confrontos_grupo_set.add((min(p.time_a_id, p.time_b_id), max(p.time_a_id, p.time_b_id)))

    def count_repeats(t1, t2, t3, t4):
        rep = 0
        if (min(t1.id, t2.id), max(t1.id, t2.id)) in confrontos_grupo_set:
            rep += 1
        if (min(t3.id, t4.id), max(t3.id, t4.id)) in confrontos_grupo_set:
            rep += 1
        return rep

    best_2nd_del = best_segundo.delegacao
    w_same = [w for w in vencedores_grupos if w.grupo_id == best_segundo.grupo_id]
    w_diff = [w for w in vencedores_grupos if w.grupo_id != best_segundo.grupo_id]

    if w_same and len(w_diff) == 2:
        # Opção 1: w_diff[0] x best_2nd E w_same[0] x w_diff[1]
        t1, t2 = w_diff[0].delegacao, best_2nd_del
        t3, t4 = w_same[0].delegacao, w_diff[1].delegacao
        if count_repeats(t1, t2, t3, t4) == 0:
            return (t1, t2), (t3, t4)

        # Opção 2: w_diff[1] x best_2nd E w_same[0] x w_diff[0]
        t1, t2 = w_diff[1].delegacao, best_2nd_del
        t3, t4 = w_same[0].delegacao, w_diff[0].delegacao
        if count_repeats(t1, t2, t3, t4) == 0:
            return (t1, t2), (t3, t4)

    # Fallback caso não seja possível evitar repetições
    todos_vencedores = [w.delegacao for w in vencedores_grupos]
    melhor_par = None
    min_rep = 999
    for w in todos_vencedores:
        outros = [t for t in todos_vencedores if t != w]
        if len(outros) >= 2:
            rep = count_repeats(w, best_2nd_del, outros[0], outros[1])
            if rep < min_rep:
                min_rep = rep
                melhor_par = ((w, best_2nd_del), (outros[0], outros[1]))

    if melhor_par:
        return melhor_par[0], melhor_par[1]

    dels = [w.delegacao for w in vencedores_grupos] + [best_2nd_del]
    return (dels[0], dels[1]), (dels[2], dels[3])


def _evitar_confrontos_mesmo_grupo(pairings, grupos_locais):
    """
    Se algum confronto colocar frente a frente equipes do mesmo grupo original,
    tenta trocar time_b com outro confronto para evitar confrontos prematuros entre equipes do mesmo grupo.
    """
    team_group = {}
    for g in grupos_locais:
        for tg in g.times.all():
            team_group[tg.delegacao_id] = g.id

    p = [list(pair) for pair in pairings]

    for i in range(len(p)):
        ta, tb = p[i]
        if not ta or not tb:
            continue
        ga, gb = team_group.get(ta.id), team_group.get(tb.id)
        if ga and gb and ga == gb:
            for j in range(len(p)):
                if i == j:
                    continue
                taj, tbj = p[j]
                if not taj or not tbj:
                    continue
                gaj, gbj = team_group.get(taj.id), team_group.get(tbj.id)
                if gbj != ga and (gb != gaj or gaj is None):
                    p[i][1] = tbj
                    p[j][1] = tb
                    break

    return [tuple(pair) for pair in p]


def _is_handebol_feminino(modalidade):
    if not modalidade:
        return False
    nome = (modalidade.nome or '').lower()
    esporte_ok = 'handebol' in nome or 'handball' in nome
    genero_ok = 'feminino' in nome or modalidade.genero == 'F'
    return esporte_ok and genero_ok


def _is_tenis_de_mesa_feminino(modalidade):
    if not modalidade:
        return False
    nome = (modalidade.nome or '').lower()
    esporte_ok = 'tênis de mesa' in nome or 'tenis de mesa' in nome
    genero_ok = 'feminino' in nome or modalidade.genero == 'F'
    return esporte_ok and genero_ok


def _is_excecao_handebol_fem(modalidade, n_diamantina, total_vagas_externas):
    return _is_handebol_feminino(modalidade) and n_diamantina == 5 and total_vagas_externas == 1


def _is_excecao_tenis_mesa_fem(modalidade, n_diamantina, total_vagas_externas):
    return _is_tenis_de_mesa_feminino(modalidade) and n_diamantina == 7 and total_vagas_externas == 2



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
    # 1. Limpa chaveamento e jogos anteriores da modalidade se existirem
    chaveamentos_antigos = ChaveamentoModalidade.objects.filter(modalidade=modalidade)
    for ch in chaveamentos_antigos:
        jogos_ids = list(ch.partidas.filter(jogo__isnull=False).values_list('jogo_id', flat=True))
        if jogos_ids:
            Jogo.objects.filter(id__in=jogos_ids).delete()
    chaveamentos_antigos.delete()

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
    # -------------------------------------------------------------
    n_diamantina = len(diamantina)

    # Exceção 1: Handebol Feminino + 5 Diamantina + 1 Vaga Externa
    if _is_excecao_handebol_fem(modalidade, n_diamantina, total_vagas_externas):
        grupo_unico = GrupoChaveamento.objects.create(
            chaveamento=chaveamento,
            nome="Grupo Único",
            campus=campus_diamantina,
            tipo="grupo_local",
            vagas_classificacao=3
        )
        shuffled_teams = list(diamantina)
        random.shuffle(shuffled_teams)
        for team in shuffled_teams:
            TimeGrupo.objects.create(grupo=grupo_unico, delegacao=team)
        _gerar_partidas_grupo(grupo_unico, fase_nome='GRUPO_LOCAL')

        _montar_fase_geral_excecao_handebol(chaveamento, classificados_externos_iniciais)
        return chaveamento

    if n_diamantina > 1:
        _construir_fase_grupos_diamantina(chaveamento, diamantina, campus_diamantina)

    # -------------------------------------------------------------
    # 4. Estrutura Completa de Mata-Mata Gerada Imediatamente
    # -------------------------------------------------------------
    is_f3g = _is_formato_3_grupos_melhor_segundo(modalidade) and n_diamantina == 9
    if is_f3g:
        num_vagas_local = 4
        classificados_local = [None] * 4
    elif n_diamantina == 1:
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
    is_excecao2 = _is_excecao_tenis_mesa_fem(chaveamento.modalidade, n, chaveamento.vagas_externas)
    is_f3g = _is_formato_3_grupos_melhor_segundo(chaveamento.modalidade) and n == 9

    # Randomiza times para distribuição justa
    shuffled_teams = list(teams)
    random.shuffle(shuffled_teams)

    # Determina a divisão dos grupos
    # Desejamos grupos de tamanho 3 ou 4.
    grupos_sizes = []

    if is_f3g:
        grupos_sizes = [3, 3, 3]
    elif is_excecao2:
        grupos_sizes = [4, 3]
    elif n <= 2:
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
        # Formato 3 Grupos de 3 (Melhor 2º Colocado Geral): 1 vaga direta por grupo
        if is_f3g:
            vagas = 1
        # Exceção 2 (Tênis de Mesa Feminino 7 Diamantina + 2 Externos): 2 vagas por grupo
        elif is_excecao2:
            vagas = 2
        elif size == 4:
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
        'gols_pro': 0, 'gols_contra': 0, 'saldo_gols': 0, 'quantidade_wo': 0
    } for tg in grupo.times.all()}

    for p in partidas:
        if p.time_a_id not in stats or p.time_b_id not in stats:
            continue

        st_a = stats[p.time_a_id]
        st_b = stats[p.time_b_id]

        if p.wo_tipo == 'AMBOS':
            # Duplo W.O.: ambos computam o jogo, mas ficam com zero pontos e com registro de WO
            st_a['jogos'] += 1
            st_b['jogos'] += 1
            st_a['derrotas'] += 1
            st_b['derrotas'] += 1
            st_a['quantidade_wo'] += 1
            st_b['quantidade_wo'] += 1
            continue

        if p.wo_tipo == 'TIME_A':
            # W.O. para o Time A: Time B tem a vitória, Time A recebe W.O.
            st_a['jogos'] += 1
            st_b['jogos'] += 1
            st_b['pontos'] += 3
            st_b['vitorias'] += 1
            st_a['derrotas'] += 1
            st_a['quantidade_wo'] += 1
            gols_a = p.placar_a if p.placar_a is not None else 0
            gols_b = p.placar_b if p.placar_b is not None else 1
            st_a['gols_pro'] += gols_a
            st_a['gols_contra'] += gols_b
            st_a['saldo_gols'] = st_a['gols_pro'] - st_a['gols_contra']
            st_b['gols_pro'] += gols_b
            st_b['gols_contra'] += gols_a
            st_b['saldo_gols'] = st_b['gols_pro'] - st_b['gols_contra']
            continue

        if p.wo_tipo == 'TIME_B':
            # W.O. para o Time B: Time A tem a vitória, Time B recebe W.O.
            st_a['jogos'] += 1
            st_b['jogos'] += 1
            st_a['pontos'] += 3
            st_a['vitorias'] += 1
            st_b['derrotas'] += 1
            st_b['quantidade_wo'] += 1
            gols_a = p.placar_a if p.placar_a is not None else 1
            gols_b = p.placar_b if p.placar_b is not None else 0
            st_a['gols_pro'] += gols_a
            st_a['gols_contra'] += gols_b
            st_a['saldo_gols'] = st_a['gols_pro'] - st_a['gols_contra']
            st_b['gols_pro'] += gols_b
            st_b['gols_contra'] += gols_a
            st_b['saldo_gols'] = st_b['gols_pro'] - st_b['gols_contra']
            continue

        if p.placar_a is None or p.placar_b is None:
            continue

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
            tg.quantidade_wo = st.get('quantidade_wo', 0)
            tg.save()


@transaction.atomic
def registrar_resultado_partida(partida, placar_a, placar_b, wo_tipo='', motivo_wo=''):
    """
    Registra o resultado de uma partida, atualiza tabelas de grupo e avança vencedores na árvore de mata-mata.
    """
    partida.wo_tipo = wo_tipo or ''
    partida.motivo_wo = motivo_wo or ''
    partida.finalizada = True

    if wo_tipo == 'TIME_A':
        partida.placar_a = placar_a if placar_a is not None else 0
        partida.placar_b = placar_b if placar_b is not None else 1
        partida.vencedor = partida.time_b
        partida.perdedor = partida.time_a
    elif wo_tipo == 'TIME_B':
        partida.placar_a = placar_a if placar_a is not None else 1
        partida.placar_b = placar_b if placar_b is not None else 0
        partida.vencedor = partida.time_a
        partida.perdedor = partida.time_b
    elif wo_tipo == 'AMBOS':
        partida.placar_a = 0
        partida.placar_b = 0
        partida.vencedor = None
        partida.perdedor = None
    else:
        partida.placar_a = placar_a
        partida.placar_b = placar_b
        if placar_a is not None and placar_b is not None:
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
        jogo.placar_time_a = partida.placar_a
        jogo.placar_time_b = partida.placar_b
        jogo.wo_tipo = partida.wo_tipo
        jogo.motivo_wo = partida.motivo_wo
        jogo.finalizado = True
        jogo.save()

    # Se for partida de grupo, atualiza a tabela do grupo e avança classificados
    if partida.grupo:
        atualizar_tabela_grupo(partida.grupo)
        atualizar_classificados_e_preencher_mata_mata(partida.chaveamento)

    # Avança vencedor para a próxima partida se configurado
    if partida.proxima_partida and partida.vencedor:
        prox = partida.proxima_partida
        if not prox.definicao_manual:
            if partida.posicao_proxima_partida == 'A':
                prox.time_a = partida.vencedor
            elif partida.posicao_proxima_partida == 'B':
                prox.time_b = partida.vencedor
            prox.save()
            _sincronizar_jogo_partida(prox, "Mata-Mata")

    # Avança perdedor para partida de perdedor (Chave Bronze / 3º lugar) se configurado
    if partida.partida_perdedor_destino and partida.perdedor:
        dest = partida.partida_perdedor_destino
        if not dest.definicao_manual:
            if partida.posicao_perdedor_destino == 'A':
                dest.time_a = partida.perdedor
            elif partida.posicao_perdedor_destino == 'B':
                dest.time_b = partida.perdedor
            dest.save()
            _sincronizar_jogo_partida(dest, "Chave Bronze / 3º Lugar")

    # Processa cumprimento de suspensões disciplinares para esta modalidade
    from core.disciplinar_services import processar_cumprimento_suspensao_partida
    processar_cumprimento_suspensao_partida(partida)

    return partida


@transaction.atomic
def atualizar_classificados_e_preencher_mata_mata(chaveamento):
    """
    Atualiza os classificados dos grupos SOMENTE quando todas as partidas do grupo forem concluídas (ou se não houver partidas no grupo).
    Preenche dinamicamente as vagas do Mata-Mata com cruzamento correto entre grupos (cruzamento olímpico),
    evitando que equipes do mesmo grupo se enfrentem prematuramente sempre que possível.
    Equipes com W.O. (quantidade_wo > 0) JAMAIS avançam para a fase seguinte; suas vagas são realocadas
    para as melhores equipes elegíveis (sem W.O.) dos demais grupos.
    """
    for g in chaveamento.grupos.all():
        atualizar_tabela_grupo(g)

    grupos_locais = list(chaveamento.grupos.filter(tipo='grupo_local').order_by('nome'))
    grupos_externos = list(chaveamento.grupos.filter(tipo='eliminatoria_ext').order_by('nome'))

    # 1. Atualiza classificados dos grupos externos (equipes com W.O. não se classificam)
    classificados_externos = []
    for g in grupos_externos:
        has_matches = g.partidas.exists()
        grupo_concluido = (not g.partidas.filter(finalizada=False).exists()) if has_matches else True
        times_ordenados = sorted(
            list(g.times.all()),
            key=lambda tg: (
                1 if tg.quantidade_wo > 0 else 0,
                -tg.pontos,
                -tg.vitorias,
                -tg.saldo_gols,
                -tg.gols_pro,
                tg.gols_contra,
                tg.id
            )
        )
        vagas = g.vagas_classificacao
        for idx, tg in enumerate(times_ordenados):
            if grupo_concluido and idx < vagas and tg.quantidade_wo == 0:
                if not tg.classificado:
                    tg.classificado = True
                    tg.save(update_fields=['classificado'])
                classificados_externos.append(tg.delegacao)
            else:
                if tg.classificado:
                    tg.classificado = False
                    tg.save(update_fields=['classificado'])
    classificados_externos = list(dict.fromkeys(classificados_externos))

    # 2. Formato 3 Grupos de 3 com Melhor 2º Colocado Geral (ex: Queimada ou configurado como tal)
    is_f3g = (
        (len(grupos_locais) == 3 and all(g.vagas_classificacao == 1 for g in grupos_locais))
        or (_is_formato_3_grupos_melhor_segundo(chaveamento.modalidade) and len(grupos_locais) == 3)
    )

    if is_f3g:
        todos_locais_concluidos = all(
            (not g.partidas.filter(finalizada=False).exists()) if g.partidas.exists() else True
            for g in grupos_locais
        )

        vencedores_grupos = []
        segundos_colocados = []

        for g in grupos_locais:
            times_ordenados = sorted(
                list(g.times.all()),
                key=lambda tg: (
                    1 if tg.quantidade_wo > 0 else 0,
                    -tg.pontos,
                    -tg.vitorias,
                    -tg.saldo_gols,
                    -tg.gols_pro,
                    tg.gols_contra,
                    tg.id
                )
            )
            times_sem_wo = [tg for tg in times_ordenados if tg.quantidade_wo == 0]
            times_com_wo = [tg for tg in times_ordenados if tg.quantidade_wo > 0]

            for tg in times_com_wo:
                if tg.classificado:
                    tg.classificado = False
                    tg.save(update_fields=['classificado'])

            if todos_locais_concluidos and times_sem_wo:
                vencedor = times_sem_wo[0]
                if not vencedor.classificado:
                    vencedor.classificado = True
                    vencedor.save(update_fields=['classificado'])
                vencedores_grupos.append(vencedor)

                if len(times_sem_wo) > 1:
                    segundo = times_sem_wo[1]
                    if segundo.classificado:
                        segundo.classificado = False
                        segundo.save(update_fields=['classificado'])
                    segundos_colocados.append(segundo)

                if len(times_sem_wo) > 2:
                    if times_sem_wo[2].classificado:
                        times_sem_wo[2].classificado = False
                        times_sem_wo[2].save(update_fields=['classificado'])
            else:
                for tg in times_ordenados:
                    if tg.classificado:
                        tg.classificado = False
                        tg.save(update_fields=['classificado'])

        # Determina o melhor 2º colocado geral (apenas entre times sem W.O.)
        best_segundo = None
        segundos_sem_wo = [s for s in segundos_colocados if s.quantidade_wo == 0]
        if todos_locais_concluidos and segundos_sem_wo:
            best_segundo = _calcular_melhor_segundo_colocado(segundos_sem_wo, chaveamento.modalidade)
            for s in segundos_colocados:
                novo_status = (best_segundo is not None and s.id == best_segundo.id)
                if s.classificado != novo_status:
                    s.classificado = novo_status
                    s.save(update_fields=['classificado'])

        # Preenche semifinais locais garantindo que o melhor 2º não enfrente o campeão do seu próprio grupo
        semis_local = list(chaveamento.partidas.filter(fase='SEMI_LOCAL').order_by('id'))
        if todos_locais_concluidos and len(vencedores_grupos) == 3 and best_segundo and len(semis_local) >= 2:
            (semi1_ta, semi1_tb), (semi2_ta, semi2_tb) = _emparelhar_semifinais_3_grupos(
                vencedores_grupos, best_segundo, chaveamento.partidas.filter(fase='GRUPO_LOCAL')
            )
            if not semis_local[0].finalizada and not semis_local[0].definicao_manual:
                semis_local[0].time_a = semi1_ta
                semis_local[0].time_b = semi1_tb
                semis_local[0].save()
                _sincronizar_jogo_partida(semis_local[0], "Semifinal 1 (Diamantina)")

            if not semis_local[1].finalizada and not semis_local[1].definicao_manual:
                semis_local[1].time_a = semi2_ta
                semis_local[1].time_b = semi2_tb
                semis_local[1].save()
                _sincronizar_jogo_partida(semis_local[1], "Semifinal 2 (Diamantina)")

        # Preenche semifinais gerais com classificados externos se aplicável
        semis_geral = list(chaveamento.partidas.filter(fase='SEMI_GERAL').order_by('id'))
        if semis_geral:
            if len(semis_geral) >= 1 and not semis_geral[0].finalizada and not semis_geral[0].definicao_manual:
                semis_geral[0].time_b = classificados_externos[0] if len(classificados_externos) >= 1 else None
                semis_geral[0].save()
                _sincronizar_jogo_partida(semis_geral[0], "Semifinal Geral 1")
            if len(semis_geral) >= 2 and not semis_geral[1].finalizada and not semis_geral[1].definicao_manual:
                semis_geral[1].time_b = classificados_externos[1] if len(classificados_externos) >= 2 else None
                semis_geral[1].save()
                _sincronizar_jogo_partida(semis_geral[1], "Semifinal Geral 2")

        return

    # 3. Formato Padrão e Demais Modalidades
    todos_locais_concluidos = all(
        (not g.partidas.filter(finalizada=False).exists()) if g.partidas.exists() else True
        for g in grupos_locais
    )

    classificados_por_grupo = {g.id: [] for g in grupos_locais}
    vagas_faltantes_por_grupo = {}
    sobras_candidatos = []

    for g in grupos_locais:
        has_matches = g.partidas.exists()
        grupo_concluido = (not g.partidas.filter(finalizada=False).exists()) if has_matches else True

        # Ordenação com prioridade absoluta para quem NÃO tem W.O.
        times_ordenados = sorted(
            list(g.times.all()),
            key=lambda tg: (
                1 if tg.quantidade_wo > 0 else 0,
                -tg.pontos,
                -tg.vitorias,
                -tg.saldo_gols,
                -tg.gols_pro,
                tg.gols_contra,
                tg.id
            )
        )

        vagas = g.vagas_classificacao
        times_sem_wo = [tg for tg in times_ordenados if tg.quantidade_wo == 0]
        times_com_wo = [tg for tg in times_ordenados if tg.quantidade_wo > 0]

        # Nenhum time com W.O. pode se classificar
        for tg in times_com_wo:
            if tg.classificado:
                tg.classificado = False
                tg.save(update_fields=['classificado'])

        # Classificação direta: até 'vagas' times sem W.O.
        diretos = times_sem_wo[:vagas] if grupo_concluido else []
        for tg in diretos:
            if not tg.classificado:
                tg.classificado = True
                tg.save(update_fields=['classificado'])
            classificados_por_grupo[g.id].append(tg.delegacao)

        # Times sem W.O. que não se classificaram diretamente no grupo
        nao_diretos = times_sem_wo[len(diretos):] if grupo_concluido else times_sem_wo
        for tg in nao_diretos:
            if tg.classificado:
                tg.classificado = False
                tg.save(update_fields=['classificado'])
            if grupo_concluido:
                sobras_candidatos.append((g, tg))

        vagas_faltantes = vagas - len(diretos)
        if vagas_faltantes > 0 and grupo_concluido:
            vagas_faltantes_por_grupo[g.id] = vagas_faltantes

    # Realocação de vagas (caso algum grupo teve W.O. e não preencheu suas vagas):
    # Desconsidera quem teve W.O. e prioriza os melhores colocados sem W.O. dos demais grupos.
    total_faltantes = sum(vagas_faltantes_por_grupo.values())
    if total_faltantes > 0 and sobras_candidatos:
        from core.models import CartaoPartida
        def _criterio_desempate_sobra(item):
            grupo_obj, tg = item
            penalidades = CartaoPartida.objects.filter(
                modalidade=chaveamento.modalidade,
                delegacao=tg.delegacao,
                partida__fase='GRUPO_LOCAL'
            ).count()
            return (
                -tg.pontos,
                -tg.vitorias,
                -tg.saldo_gols,
                -tg.gols_pro,
                tg.gols_contra,
                penalidades,
                tg.id
            )

        sobras_candidatos.sort(key=_criterio_desempate_sobra)
        repescados_selecionados = sobras_candidatos[:total_faltantes]

        # Marca os repescados como classificados
        for g_origem, tg in repescados_selecionados:
            tg.classificado = True
            tg.save(update_fields=['classificado'])

        # Aloca cada repescado para preencher as vagas faltantes dos grupos
        # Prioriza alocar em grupo DIFERENTE do grupo de origem do time repescado
        repescados_restantes = list(repescados_selecionados)
        for g_id, faltam in list(vagas_faltantes_por_grupo.items()):
            for _ in range(faltam):
                if not repescados_restantes:
                    break
                escolhido = None
                for cand in repescados_restantes:
                    if cand[0].id != g_id:
                        escolhido = cand
                        break
                if not escolhido:
                    escolhido = repescados_restantes[0]
                repescados_restantes.remove(escolhido)
                classificados_por_grupo[g_id].append(escolhido[1].delegacao)

    todos_classificados_diamantina = []
    for g in grupos_locais:
        for tg in sorted(g.times.filter(classificado=True), key=lambda x: (
            -x.pontos, -x.vitorias, -x.saldo_gols, -x.gols_pro, x.gols_contra
        )):
            if tg.delegacao not in todos_classificados_diamantina:
                todos_classificados_diamantina.append(tg.delegacao)

    quartas = list(chaveamento.partidas.filter(fase='QUARTAS_LOCAL').order_by('id'))
    semis_local = list(chaveamento.partidas.filter(fase='SEMI_LOCAL').order_by('id'))
    semis_geral = list(chaveamento.partidas.filter(fase='SEMI_GERAL').order_by('id'))
    final_local = chaveamento.partidas.filter(fase='FINAL_LOCAL').first()

    num_grupos = len(grupos_locais)

    # -----------------------------------------------------------------
    # Cenário A: Existem Quartas de Final (QUARTAS_LOCAL)
    # -----------------------------------------------------------------
    if quartas:
        q_pairings = []
        if num_grupos == 2:
            g_a = grupos_locais[0]
            g_b = grupos_locais[1]
            c_a = classificados_por_grupo.get(g_a.id, [])
            c_b = classificados_por_grupo.get(g_b.id, [])

            t1_a = c_a[0] if len(c_a) >= 1 else None
            t2_a = c_a[1] if len(c_a) >= 2 else None
            t3_a = c_a[2] if len(c_a) >= 3 else None
            t4_a = c_a[3] if len(c_a) >= 4 else None

            t1_b = c_b[0] if len(c_b) >= 1 else None
            t2_b = c_b[1] if len(c_b) >= 2 else None
            t3_b = c_b[2] if len(c_b) >= 3 else None
            t4_b = c_b[3] if len(c_b) >= 4 else None

            # Cruzamento Olímpico de Quartas:
            # Q1: 1ºA x 4ºB -> alimenta Semi 1 (A)
            # Q2: 2ºB x 3ºA -> alimenta Semi 1 (B)
            # Q3: 1ºB x 4ºA -> alimenta Semi 2 (A)
            # Q4: 2ºA x 3ºB -> alimenta Semi 2 (B)
            q_pairings = [
                (t1_a, t4_b),
                (t2_b, t3_a),
                (t1_b, t4_a),
                (t2_a, t3_b),
            ]

        elif num_grupos == 3:
            g_a = grupos_locais[0]
            g_b = grupos_locais[1]
            g_c = grupos_locais[2]
            c_a = classificados_por_grupo.get(g_a.id, [])
            c_b = classificados_por_grupo.get(g_b.id, [])
            c_c = classificados_por_grupo.get(g_c.id, [])

            t1_a = c_a[0] if len(c_a) >= 1 else None
            t2_a = c_a[1] if len(c_a) >= 2 else None
            t3_a = c_a[2] if len(c_a) >= 3 else None

            t1_b = c_b[0] if len(c_b) >= 1 else None
            t2_b = c_b[1] if len(c_b) >= 2 else None
            t3_b = c_b[2] if len(c_b) >= 3 else None

            t1_c = c_c[0] if len(c_c) >= 1 else None
            t2_c = c_c[1] if len(c_c) >= 2 else None
            t3_c = c_c[2] if len(c_c) >= 3 else None

            if not t3_b and t3_c:
                t3_b = t3_c
                t3_c = None
            if not t3_a and t3_c:
                t3_a = t3_c
                t3_c = None

            # Q1: 1ºA x 3ºB (ou Bye caso não haja 3ºB) -> alimenta Semi 1 (A)
            # Q2: 2ºB x 2ºC (Cruzamento -> alimenta Semi 1 B)
            # Q3: 1ºB x 3ºA (ou Bye caso não haja 3ºA) -> alimenta Semi 2 (A)
            # Q4: 1ºC x 2ºA (Cruzamento -> alimenta Semi 2 B)
            q_pairings = [
                (t1_a, t3_b),
                (t2_b, t2_c),
                (t1_b, t3_a),
                (t1_c, t2_a),
            ]

        elif num_grupos == 4:
            c_a = classificados_por_grupo.get(grupos_locais[0].id, [])
            c_b = classificados_por_grupo.get(grupos_locais[1].id, [])
            c_c = classificados_por_grupo.get(grupos_locais[2].id, [])
            c_d = classificados_por_grupo.get(grupos_locais[3].id, [])

            t1_a = c_a[0] if len(c_a) >= 1 else None
            t2_a = c_a[1] if len(c_a) >= 2 else None
            t1_b = c_b[0] if len(c_b) >= 1 else None
            t2_b = c_b[1] if len(c_b) >= 2 else None
            t1_c = c_c[0] if len(c_c) >= 1 else None
            t2_c = c_c[1] if len(c_c) >= 2 else None
            t1_d = c_d[0] if len(c_d) >= 1 else None
            t2_d = c_d[1] if len(c_d) >= 2 else None

            # Q1: 1ºA x 2ºB
            # Q2: 1ºC x 2ºD
            # Q3: 1ºB x 2ºA
            # Q4: 1ºD x 2ºC
            q_pairings = [
                (t1_a, t2_b),
                (t1_c, t2_d),
                (t1_b, t2_a),
                (t1_d, t2_c),
            ]

        else:
            # Grupo Único ou formato genérico
            pairings = [(0, 7), (3, 4), (1, 6), (2, 5)]
            for idx_a, idx_b in pairings:
                ta = todos_classificados_diamantina[idx_a] if idx_a < len(todos_classificados_diamantina) else None
                tb = todos_classificados_diamantina[idx_b] if idx_b < len(todos_classificados_diamantina) else None
                q_pairings.append((ta, tb))

        # Evita que equipes do mesmo grupo se enfrentem prematuramente nas Quartas
        q_pairings = _evitar_confrontos_mesmo_grupo(q_pairings, grupos_locais)

        for i, q in enumerate(quartas):
            if i >= len(q_pairings):
                break
            ta, tb = q_pairings[i]

            # Se a partida foi definida manualmente pela organização, não altera times nem status
            if q.definicao_manual:
                continue

            # Se a partida foi finalizada anteriormente por Bye (sem placar e sem W.O.),
            # mas agora ambos os adversários estão definidos, desfaz o Bye para que o jogo aconteça:
            if q.finalizada and q.placar_a is None and q.placar_b is None and not q.wo_tipo and ta and tb:
                q.finalizada = False
                q.vencedor = None
                q.perdedor = None
                if q.proxima_partida and not q.proxima_partida.finalizada and not q.proxima_partida.definicao_manual:
                    if q.posicao_proxima_partida == 'A' and q.proxima_partida.time_a == ta:
                        q.proxima_partida.time_a = None
                        q.proxima_partida.save(update_fields=['time_a'])
                    elif q.posicao_proxima_partida == 'B' and q.proxima_partida.time_b == ta:
                        q.proxima_partida.time_b = None
                        q.proxima_partida.save(update_fields=['time_b'])

            if not q.finalizada:
                q.time_a = ta
                q.time_b = tb

                # Bye definitivo: se ta existe e tb não existe, e todos os grupos estão concluídos:
                if ta and not tb and todos_locais_concluidos:
                    q.vencedor = ta
                    q.finalizada = True
                    if i == 0 and semis_local and len(semis_local) >= 1 and not semis_local[0].finalizada and not semis_local[0].definicao_manual:
                        semis_local[0].time_a = ta
                        semis_local[0].save(update_fields=['time_a'])
                        _sincronizar_jogo_partida(semis_local[0], "Semifinal 1 (Diamantina)")
                    elif i == 1 and semis_local and len(semis_local) >= 1 and not semis_local[0].finalizada and not semis_local[0].definicao_manual:
                        semis_local[0].time_b = ta
                        semis_local[0].save(update_fields=['time_b'])
                        _sincronizar_jogo_partida(semis_local[0], "Semifinal 1 (Diamantina)")
                    elif i == 2 and semis_local and len(semis_local) >= 2 and not semis_local[1].finalizada and not semis_local[1].definicao_manual:
                        semis_local[1].time_a = ta
                        semis_local[1].save(update_fields=['time_a'])
                        _sincronizar_jogo_partida(semis_local[1], "Semifinal 2 (Diamantina)")
                    elif i == 3 and semis_local and len(semis_local) >= 2 and not semis_local[1].finalizada and not semis_local[1].definicao_manual:
                        semis_local[1].time_b = ta
                        semis_local[1].save(update_fields=['time_b'])
                        _sincronizar_jogo_partida(semis_local[1], "Semifinal 2 (Diamantina)")

                q.save()
                _sincronizar_jogo_partida(q, f"Quartas {i+1} (Diamantina)")

    # -----------------------------------------------------------------
    # Cenário B: Não há Quartas, mas há Semifinais Locais (SEMI_LOCAL)
    # -----------------------------------------------------------------
    elif semis_local:
        s_pairings = []
        if num_grupos == 2:
            g_a = grupos_locais[0]
            g_b = grupos_locais[1]
            c_a = classificados_por_grupo.get(g_a.id, [])
            c_b = classificados_por_grupo.get(g_b.id, [])

            t1_a = c_a[0] if len(c_a) >= 1 else None
            t2_a = c_a[1] if len(c_a) >= 2 else None
            t1_b = c_b[0] if len(c_b) >= 1 else None
            t2_b = c_b[1] if len(c_b) >= 2 else None

            # Cruzamento Olímpico Semifinais:
            # Semi 1: 1ºA x 2ºB
            # Semi 2: 1ºB x 2ºA
            s_pairings = [
                (t1_a, t2_b),
                (t1_b, t2_a)
            ]

        elif num_grupos == 4:
            c_a = classificados_por_grupo.get(grupos_locais[0].id, [])
            c_b = classificados_por_grupo.get(grupos_locais[1].id, [])
            c_c = classificados_por_grupo.get(grupos_locais[2].id, [])
            c_d = classificados_por_grupo.get(grupos_locais[3].id, [])

            t1_a = c_a[0] if len(c_a) >= 1 else None
            t1_b = c_b[0] if len(c_b) >= 1 else None
            t1_c = c_c[0] if len(c_c) >= 1 else None
            t1_d = c_d[0] if len(c_d) >= 1 else None

            s_pairings = [
                (t1_a, t1_d),
                (t1_b, t1_c)
            ]

        else:
            # Grupo Único ou formato genérico
            s_pairings = [
                (todos_classificados_diamantina[0] if len(todos_classificados_diamantina) >= 1 else None,
                 todos_classificados_diamantina[3] if len(todos_classificados_diamantina) >= 4 else None),
                (todos_classificados_diamantina[1] if len(todos_classificados_diamantina) >= 2 else None,
                 todos_classificados_diamantina[2] if len(todos_classificados_diamantina) >= 3 else None)
            ]

        s_pairings = _evitar_confrontos_mesmo_grupo(s_pairings, grupos_locais)

        if len(semis_local) >= 1 and not semis_local[0].finalizada and not semis_local[0].definicao_manual:
            semis_local[0].time_a = s_pairings[0][0]
            semis_local[0].time_b = s_pairings[0][1]
            semis_local[0].save()
            _sincronizar_jogo_partida(semis_local[0], "Semifinal 1 (Diamantina)")

        if len(semis_local) >= 2 and not semis_local[1].finalizada and not semis_local[1].definicao_manual:
            semis_local[1].time_a = s_pairings[1][0]
            semis_local[1].time_b = s_pairings[1][1]
            semis_local[1].save()
            _sincronizar_jogo_partida(semis_local[1], "Semifinal 2 (Diamantina)")

    # -----------------------------------------------------------------
    # Cenário C: Não há Quartas nem Semis, mas há Final Local (FINAL_LOCAL)
    # -----------------------------------------------------------------
    elif final_local and not quartas and not semis_local:
        if not final_local.finalizada and not final_local.definicao_manual:
            if num_grupos == 2:
                g_a = grupos_locais[0]
                g_b = grupos_locais[1]
                c_a = classificados_por_grupo.get(g_a.id, [])
                c_b = classificados_por_grupo.get(g_b.id, [])

                final_local.time_a = c_a[0] if len(c_a) >= 1 else None
                final_local.time_b = c_b[0] if len(c_b) >= 1 else None
            else:
                final_local.time_a = todos_classificados_diamantina[0] if len(todos_classificados_diamantina) >= 1 else None
                final_local.time_b = todos_classificados_diamantina[1] if len(todos_classificados_diamantina) >= 2 else None

            final_local.save()
            _sincronizar_jogo_partida(final_local, "Final de Diamantina")

    # -----------------------------------------------------------------
    # Cenário D: Semifinais Gerais (SEMI_GERAL)
    # -----------------------------------------------------------------
    if semis_geral:
        if not final_local and not semis_local and not quartas and len(todos_classificados_diamantina) >= 3:
            if not semis_geral[0].finalizada and not semis_geral[0].definicao_manual:
                semis_geral[0].time_a = todos_classificados_diamantina[0] if len(todos_classificados_diamantina) >= 1 else None
                semis_geral[0].time_b = classificados_externos[0] if len(classificados_externos) >= 1 else None
                semis_geral[0].save()
                _sincronizar_jogo_partida(semis_geral[0], "Semifinal Geral 1")

            if not semis_geral[1].finalizada and not semis_geral[1].definicao_manual:
                semis_geral[1].time_a = todos_classificados_diamantina[1] if len(todos_classificados_diamantina) >= 2 else None
                semis_geral[1].time_b = todos_classificados_diamantina[2] if len(todos_classificados_diamantina) >= 3 else None
                semis_geral[1].save()
                _sincronizar_jogo_partida(semis_geral[1], "Semifinal Geral 2")
        else:
            if len(semis_geral) >= 1 and not semis_geral[0].finalizada and not semis_geral[0].definicao_manual:
                semis_geral[0].time_b = classificados_externos[0] if len(classificados_externos) >= 1 else None
                semis_geral[0].save()
                _sincronizar_jogo_partida(semis_geral[0], "Semifinal Geral 1")
            if len(semis_geral) >= 2 and not semis_geral[1].finalizada and not semis_geral[1].definicao_manual:
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


def _montar_fase_geral_excecao_handebol(chaveamento, classificados_externos):
    """
    Integra a Fase Geral para a Exceção de Handebol Feminino (5 equipes de Diamantina + 1 vaga externa).
    Os 3 primeiros colocados de Diamantina vão direto para a Fase Geral sem mata-mata local.
    """
    ext1 = classificados_externos[0] if len(classificados_externos) > 0 else None

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
        proxima_partida=final_geral,
        posicao_proxima_partida='B',
        partida_perdedor_destino=chave_bronze,
        posicao_perdedor_destino='B'
    )
    _sincronizar_jogo_partida(semi_geral_2, "Semifinal Geral 2")

    # Conecta partidas de eliminatória externa à Semi Geral 1 (posição B) se aplicável
    partidas_ext = PartidaChaveamento.objects.filter(
        chaveamento=chaveamento,
        fase='EXTERNO_ELIMINATORIA'
    )
    for p_ext in partidas_ext:
        p_ext.proxima_partida = semi_geral_1
        p_ext.posicao_proxima_partida = 'B'
        p_ext.save()



def _sincronizar_jogo_partida(partida, descricao_local="Quadra Principal"):
    """
    Garante que uma PartidaChaveamento tenha um Jogo correspondente no sistema apenas quando ambas as delegações estiverem definidas.
    Se o Jogo já existir mas ainda não foi finalizado, atualiza seus times ou remove-o caso um dos adversários volte a ficar indefinido.
    """
    if partida.finalizada:
        return

    if partida.jogo:
        if not partida.jogo.finalizado:
            if partida.time_a and partida.time_b and partida.time_a != partida.time_b:
                if partida.jogo.time_a != partida.time_a or partida.jogo.time_b != partida.time_b:
                    partida.jogo.time_a = partida.time_a
                    partida.jogo.time_b = partida.time_b
                    partida.jogo.save(update_fields=['time_a', 'time_b'])
            else:
                jogo_to_delete = partida.jogo
                partida.jogo = None
                partida.save(update_fields=['jogo'])
                jogo_to_delete.delete()
    elif partida.time_a and partida.time_b and partida.time_a != partida.time_b:
        hoje = timezone.localdate()
        jogo = Jogo.objects.create(
            modalidade=partida.chaveamento.modalidade,
            data_jogo=partida.data_partida or hoje,
            horario_jogo=partida.horario_partida,
            time_a=partida.time_a,
            time_b=partida.time_b,
            local=descricao_local
        )
        partida.jogo = jogo
        partida.save(update_fields=['jogo'])
