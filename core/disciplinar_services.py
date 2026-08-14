from django.db import models
from core.models import RegistroDisciplinarAtleta, CartaoPartida, PartidaChaveamento, Atleta, Modalidade

def registrar_cartao_atleta(partida, atleta, tipo_cartao, minuto=None, observacao=None):
    """
    Registra um cartão para um atleta em uma partida e recalcula a situação disciplinar.
    A comissão/mesário seleciona apenas 'AMARELO' ou 'VERMELHO'.
    O sistema detecta automaticamente se o atleta já possuía um amarelo NESTA MESMA partida
    e converte para 'SEGUNDO_AMARELO' (expulsão e suspensão de 1 jogo).
    """
    modalidade = partida.modalidade if hasattr(partida, 'modalidade') and partida.modalidade else (
        partida.chaveamento.modalidade if getattr(partida, 'chaveamento', None) else (partida.jogo.modalidade if getattr(partida, 'jogo', None) else None)
    )
    if not modalidade:
        raise ValueError("A partida deve possuir uma modalidade vinculada.")

    times_partida = [t for t in [getattr(partida, 'time_a', None), getattr(partida, 'time_b', None)] if t]
    if times_partida:
        times_ids = set()
        for t in times_partida:
            times_ids.add(t.id)
            if getattr(t, 'parent_delegate_id', None):
                times_ids.add(t.parent_delegate_id)
            if hasattr(t, 'sub_delegados'):
                times_ids.update(t.sub_delegados.values_list('id', flat=True))

        atleta_del_ids = {atleta.cadastrado_por_id}
        if getattr(atleta.cadastrado_por, 'parent_delegate_id', None):
            atleta_del_ids.add(atleta.cadastrado_por.parent_delegate_id)

        # Checar se o atleta está inscrito em alguma delegação desta partida
        inscricao_del_ids = set(atleta.modalidades_inscritas.values_list('inscricao__delegacao_id', flat=True))
        atleta_del_ids.update(inscricao_del_ids)

        if not (atleta_del_ids & times_ids):
            nomes = " ou ".join([getattr(t, 'nome_delegacao', None) or t.email for t in times_partida])
            raise ValueError(f"O atleta '{atleta.nome_completo}' não pertence às delegações desta partida ({nomes}).")

    delegacao = atleta.cadastrado_por.delegacao_ativa if hasattr(atleta.cadastrado_por, 'delegacao_ativa') else atleta.cadastrado_por

    # Se o cartão for amarelo, verifica se já existe um amarelo lançado para este atleta nesta mesma partida
    if tipo_cartao == 'AMARELO':
        ja_tem_amarelo = CartaoPartida.objects.filter(
            partida=partida,
            atleta=atleta,
            tipo__in=['AMARELO', 'SEGUNDO_AMARELO']
        ).exists()
        if ja_tem_amarelo:
            tipo_cartao = 'SEGUNDO_AMARELO'

    cartao = CartaoPartida.objects.create(
        partida=partida,
        jogo=partida.jogo if partida else None,
        atleta=atleta,
        delegacao=delegacao,
        modalidade=modalidade,
        tipo=tipo_cartao,
        minuto=minuto,
        observacao=observacao
    )

    recalcular_disciplinar_atleta_modalidade(atleta, modalidade)
    return cartao


def remover_cartao_atleta(cartao_id):
    """
    Remove um cartão registrado e recalcula o histórico disciplinar do atleta.
    """
    try:
        cartao = CartaoPartida.objects.get(pk=cartao_id)
        atleta = cartao.atleta
        modalidade = cartao.modalidade or (cartao.partida.chaveamento.modalidade if cartao.partida and cartao.partida.chaveamento else None)
        cartao.delete()
        if atleta and modalidade:
            recalcular_disciplinar_atleta_modalidade(atleta, modalidade)
        return True
    except CartaoPartida.DoesNotExist:
        return False


def recalcular_disciplinar_atleta_modalidade(atleta, modalidade):
    """
    Recalcula integralmente o estado disciplinar do atleta para uma modalidade específica:
    - Cartões amarelos acumulados (reset a cada 2 amarelos acumulados em partidas diferentes).
    - Suspensões pendentes por 2º amarelo acumulado, 2º amarelo na mesma partida e vermelho direto.
    - Cumprimento de suspensões em partidas finalizadas da equipe daquela modalidade.
    """
    registro, _ = RegistroDisciplinarAtleta.objects.get_or_create(
        atleta=atleta,
        modalidade=modalidade
    )

    # Reset contadores
    registro.cartoes_amarelos_acumulados = 0
    registro.suspenso_jogos_pendentes = 0
    registro.total_amarelos_historico = 0
    registro.total_vermelhos_historico = 0
    registro.total_jogos_suspensao_cumpridos = 0

    delegacao = atleta.cadastrado_por.delegacao_ativa if hasattr(atleta.cadastrado_por, 'delegacao_ativa') else atleta.cadastrado_por

    delegacao_ids = {delegacao.id}
    if hasattr(delegacao, 'sub_delegados'):
        delegacao_ids.update(delegacao.sub_delegados.values_list('id', flat=True))
    if getattr(delegacao, 'parent_delegate_id', None):
        delegacao_ids.add(delegacao.parent_delegate_id)
    if atleta.cadastrado_por_id:
        delegacao_ids.add(atleta.cadastrado_por_id)

    # Buscar todas as partidas do chaveamento desta modalidade envolvendo a delegação do atleta
    partidas = (
        PartidaChaveamento.objects.filter(chaveamento__modalidade=modalidade, time_a_id__in=delegacao_ids) |
        PartidaChaveamento.objects.filter(chaveamento__modalidade=modalidade, time_b_id__in=delegacao_ids)
    ).order_by('id').distinct()

    for partida in partidas:
        cartoes_nesta_partida = list(CartaoPartida.objects.filter(partida=partida, atleta=atleta).order_by('criado_em', 'id'))

        # Se o atleta tinha suspensão pendente ANTES desta partida e ela foi finalizada,
        # ele cumpre 1 jogo de suspensão nesta partida (desde que não tenha recebido cartão nela)
        if partida.finalizada and registro.suspenso_jogos_pendentes > 0 and not cartoes_nesta_partida:
            registro.suspenso_jogos_pendentes -= 1
            registro.total_jogos_suspensao_cumpridos += 1

        # Processa os cartões aplicados nesta partida com inteligência de contagem
        amarelos_na_partida = 0
        for cartao in cartoes_nesta_partida:
            if cartao.tipo in ['AMARELO', 'SEGUNDO_AMARELO']:
                amarelos_na_partida += 1
                if amarelos_na_partida == 1:
                    # 1º Amarelo no jogo
                    if cartao.tipo != 'AMARELO':
                        cartao.tipo = 'AMARELO'
                        cartao.save(update_fields=['tipo'])
                    registro.total_amarelos_historico += 1
                    registro.cartoes_amarelos_acumulados += 1
                    if registro.cartoes_amarelos_acumulados >= 2:
                        registro.suspenso_jogos_pendentes += 1
                        registro.cartoes_amarelos_acumulados = 0  # Zerado após gerar suspensão por 2º amarelo acumulado em partidas diferentes
                else:
                    # 2º Amarelo no MESMO jogo (Expulsão por 2º amarelo)
                    if cartao.tipo != 'SEGUNDO_AMARELO':
                        cartao.tipo = 'SEGUNDO_AMARELO'
                        cartao.save(update_fields=['tipo'])
                    registro.total_amarelos_historico += 1
                    registro.total_vermelhos_historico += 1
                    registro.suspenso_jogos_pendentes += 1
                    # Não incrementa cartoes_amarelos_acumulados para outra suspensão

            elif cartao.tipo == 'VERMELHO':
                registro.total_vermelhos_historico += 1
                registro.suspenso_jogos_pendentes += 1
                # Vermelho gera 1 jogo de suspensão; amarelos acumulados anteriores permanecem válidos no histórico

    registro.save()
    return registro


def processar_cumprimento_suspensao_partida(partida):
    """
    Disparado quando uma partida é finalizada (resultado salvo).
    Recalcula a situação disciplinar de todos os atletas das delegações da partida.
    """
    modalidade = partida.chaveamento.modalidade if partida.chaveamento else (partida.jogo.modalidade if partida.jogo else None)
    if not modalidade:
        return

    times = [partida.time_a, partida.time_b]
    for team in times:
        if not team:
            continue
        team_ids = [team.id]
        if getattr(team, 'parent_delegate_id', None):
            team_ids.append(team.parent_delegate_id)
        if hasattr(team, 'sub_delegados'):
            team_ids.extend(list(team.sub_delegados.values_list('id', flat=True)))

        atletas = Atleta.objects.filter(
            models.Q(cadastrado_por_id__in=team_ids) |
            models.Q(modalidades_inscritas__inscricao__delegacao_id__in=team_ids),
            modalidades_inscritas__modalidade=modalidade
        ).distinct()
        for atleta in atletas:
            recalcular_disciplinar_atleta_modalidade(atleta, modalidade)


def obter_relatorio_disciplinar_modalidade(modalidade):
    """
    Retorna o resumo disciplinar completo para a modalidade:
    - Lista de registros disciplinares com cartões ativos e suspensões.
    - Histórico de todos os cartões aplicados na modalidade.
    """
    registros = RegistroDisciplinarAtleta.objects.filter(
        modalidade=modalidade
    ).select_related('atleta', 'atleta__cadastrado_por', 'atleta__campus').order_by('-suspenso_jogos_pendentes', '-cartoes_amarelos_acumulados', 'atleta__nome_completo')

    cartoes = CartaoPartida.objects.filter(
        modalidade=modalidade
    ).select_related('atleta', 'delegacao', 'partida').order_by('-criado_em')

    atletas_suspensos = [r for r in registros if r.suspenso_jogos_pendentes > 0]
    atletas_com_amarelos = [r for r in registros if r.cartoes_amarelos_acumulados > 0]

    return {
        'registros': registros,
        'cartoes': cartoes,
        'atletas_suspensos': atletas_suspensos,
        'atletas_com_amarelos': atletas_com_amarelos,
    }
