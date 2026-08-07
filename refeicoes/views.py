import json
import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import IntegrityError
from django.db.models import Q, Count

from .models import RefeicaoAgendada, RegistroRefeicao
from .forms import RefeicaoAgendadaForm
from core.models import Atleta, Campus
from users.models import User


def comissao_required(view_func):
    """
    Decorator para verificar se o usuário pertence à comissão organizadora.
    """
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if not getattr(request.user, 'is_comissao', False) and not request.user.is_staff:
            messages.error(request, "Acesso restrito à Comissão Organizadora.")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def get_delegacao_nome_atleta(atleta):
    """
    Auxiliar seguro para obter o nome da delegação do criador do atleta.
    """
    if atleta and atleta.cadastrado_por:
        del_user = getattr(atleta.cadastrado_por, 'delegacao_ativa', None)
        if del_user:
            nome = getattr(del_user, 'nome_delegacao', None)
            if nome:
                return nome
    return "Sem Delegação"


@comissao_required
def gerenciar_refeicoes_view(request):
    """
    Lista e permite cadastrar/agendar refeições e definir quais campi têm acesso.
    """
    if request.method == 'POST':
        form = RefeicaoAgendadaForm(request.POST)
        if form.is_valid():
            try:
                refeicao = form.save(commit=False)
                refeicao.criado_por = request.user
                refeicao.save()
                form.save_m2m()
                messages.success(request, f"Refeição '{refeicao.get_tipo_display()}' agendada com sucesso para {refeicao.data.strftime('%d/%m/%Y')}!")
                return redirect('refeicoes_gerenciar')
            except IntegrityError:
                messages.error(request, "Já existe uma refeição agendada com o mesmo tipo nesta mesma data.")
        else:
            messages.error(request, "Erros no formulário. Verifique os campos.")
    else:
        form = RefeicaoAgendadaForm()

    hoje = timezone.localdate()
    refeicoes_hoje = RefeicaoAgendada.objects.filter(data=hoje).prefetch_related('campi_liberados')
    refeicoes_todas = RefeicaoAgendada.objects.all().prefetch_related('campi_liberados', 'registros')[:30]

    context = {
        'form': form,
        'hoje': hoje,
        'refeicoes_hoje': refeicoes_hoje,
        'refeicoes_todas': refeicoes_todas,
    }
    return render(request, 'refeicoes/gerenciar.html', context)


@comissao_required
def editar_refeicao_view(request, refeicao_id):
    """
    Permite editar uma refeição agendada (ajustar campi liberados, tipo, data ou status).
    """
    refeicao = get_object_or_404(RefeicaoAgendada, id=refeicao_id)
    
    if request.method == 'POST':
        form = RefeicaoAgendadaForm(request.POST, instance=refeicao)
        if form.is_valid():
            try:
                refeicao_salva = form.save()
                messages.success(request, f"Refeição '{refeicao_salva.get_tipo_display()}' atualizada com sucesso!")
                return redirect('refeicoes_gerenciar')
            except IntegrityError:
                messages.error(request, "Já existe uma refeição agendada com este mesmo tipo nesta data.")
        else:
            messages.error(request, "Erros no formulário de edição.")
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('json') == '1':
        campi_liberados = list(refeicao.campi_liberados.values_list('id', flat=True))
        return JsonResponse({
            'id': refeicao.id,
            'data': refeicao.data.strftime('%Y-%m-%d'),
            'tipo': refeicao.tipo,
            'ativo': refeicao.ativo,
            'campi_liberados': campi_liberados,
            'tipo_display': refeicao.get_tipo_display(),
            'campi_nomes': [c.nome for c in refeicao.campi_liberados.all()],
        })

    return redirect('refeicoes_gerenciar')


@comissao_required
@require_POST
def toggle_refeicao_ativa_view(request, refeicao_id):
    """
    Alterna o status ativo/inativo de um agendamento de refeição.
    """
    refeicao = get_object_or_404(RefeicaoAgendada, id=refeicao_id)
    hoje = timezone.localdate()
    if refeicao.data < hoje:
        messages.error(request, "Esta refeição é de uma data passada e está encerrada.")
        return redirect('refeicoes_gerenciar')

    refeicao.ativo = not refeicao.ativo
    refeicao.save()
    status_str = "ativada" if refeicao.ativo else "desativada"
    messages.success(request, f"Refeição {refeicao.get_tipo_display()} ({refeicao.data.strftime('%d/%m/%Y')}) {status_str}!")
    return redirect('refeicoes_gerenciar')


@comissao_required
def validar_refeicao_view(request):
    """
    Interface administrativa para busca e validação manual por Nome, CPF ou Matrícula do atleta.
    Exibe no seletor APENAS as refeições ativas agendadas para a data de hoje.
    """
    hoje = timezone.localdate()
    refeicoes_ativas = RefeicaoAgendada.objects.filter(data=hoje, ativo=True).prefetch_related('campi_liberados')

    context = {
        'refeicoes_ativas': refeicoes_ativas,
        'hoje': hoje,
    }
    return render(request, 'refeicoes/validar.html', context)


@comissao_required
def api_buscar_atletas(request):
    """
    Busca dinâmica de atletas por Nome, CPF ou Matrícula via AJAX.
    Exclui da busca atletas cujo campus NÃO esteja liberado para a refeição selecionada.
    """
    q = request.GET.get('q', '').strip()
    refeicao_id = request.GET.get('refeicao_id')

    if not q or len(q) < 2:
        return JsonResponse({'atletas': []})

    clean_q = ''.join(filter(str.isdigit, q))

    filtros = Q(nome_completo__icontains=q) | Q(matricula__icontains=q)
    if clean_q:
        filtros |= Q(cpf__icontains=clean_q)

    # EXCLUSÃO DA QUERY: se a refeição especifica campi liberados, oculta atletas de outros campi
    if refeicao_id and str(refeicao_id).isdigit():
        refeicao_obj = RefeicaoAgendada.objects.filter(id=int(refeicao_id)).first()
        if refeicao_obj and refeicao_obj.campi_liberados.exists():
            campi_permitidos_ids = list(refeicao_obj.campi_liberados.values_list('id', flat=True))
            filtros &= Q(campus_id__in=campi_permitidos_ids)

    atletas = Atleta.objects.filter(filtros).select_related('campus', 'cadastrado_por')[:15]

    hoje = timezone.localdate()
    refeicoes_hoje = RefeicaoAgendada.objects.filter(data=hoje, ativo=True).prefetch_related('campi_liberados')
    
    registros_hoje = RegistroRefeicao.objects.filter(refeicao__data=hoje).select_related('refeicao')
    retiradas_dict = {(r.atleta_id, r.refeicao.tipo): timezone.localtime(r.data_retirada).strftime('%H:%M') for r in registros_hoje}

    data = []
    for a in atletas:
        delegacao_nome = get_delegacao_nome_atleta(a)
        
        status_refeicoes = []
        for ref in refeicoes_hoje:
            hora_retirada = retiradas_dict.get((a.id, ref.tipo))
            campus_liberado = not ref.campi_liberados.exists() or (a.campus and a.campus in ref.campi_liberados.all())
            status_refeicoes.append({
                'refeicao_id': ref.id,
                'tipo_code': ref.tipo,
                'tipo_nome': ref.get_tipo_display(),
                'retirado': bool(hora_retirada),
                'hora_retirada': hora_retirada or '',
                'liberado': campus_liberado,
            })

        data.append({
            'id': a.id,
            'nome_completo': a.nome_completo,
            'cpf': a.cpf or "-",
            'matricula': a.matricula,
            'campus_id': a.campus_id,
            'campus_nome': a.campus.nome if a.campus else "Sem Campus",
            'delegacao': delegacao_nome,
            'tipo_atleta': a.get_tipo_atleta_display(),
            'status_refeicoes': status_refeicoes,
        })

    return JsonResponse({'atletas': data})


@comissao_required
@require_POST
def api_processar_validacao(request):
    """
    Endpoint AJAX para registrar a retirada de refeição por um atleta.
    Garante tratamento rigoroso de exceções retornando mensagens tratadas em JSON.
    """
    try:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = request.POST

        atleta_id = data.get('atleta_id')
        refeicao_id = data.get('refeicao_id')
        raw_query = str(data.get('query') or '').strip()

        if not refeicao_id or not str(refeicao_id).isdigit():
            return JsonResponse({'success': False, 'message': 'Selecione uma refeição ativa para validação.'}, status=400)

        refeicao = RefeicaoAgendada.objects.filter(id=int(refeicao_id)).first()
        if not refeicao:
            return JsonResponse({'success': False, 'message': 'Refeição agendada não encontrada.'}, status=404)

        if not refeicao.ativo:
            return JsonResponse({'success': False, 'message': 'Esta refeição não está ativa para validação.'}, status=400)

        atleta = None
        if atleta_id:
            atleta = Atleta.objects.filter(id=atleta_id).select_related('campus', 'cadastrado_por').first()
        elif raw_query:
            clean_digits = ''.join(filter(str.isdigit, raw_query))
            atleta = Atleta.objects.filter(
                Q(id=int(raw_query) if raw_query.isdigit() else -1) |
                Q(matricula__iexact=raw_query) |
                Q(cpf__icontains=clean_digits if clean_digits else '___')
            ).select_related('campus', 'cadastrado_por').first()

        if not atleta:
            return JsonResponse({
                'success': False, 
                'message': f'Atleta não encontrado para os dados informados: "{raw_query or atleta_id}".'
            }, status=404)

        # VALIDAÇÃO 1: Verificar se o Campus do Atleta está liberado
        campi_liberados_ids = list(refeicao.campi_liberados.values_list('id', flat=True))
        if campi_liberados_ids and (not atleta.campus or atleta.campus.id not in campi_liberados_ids):
            campus_atleta_nome = atleta.campus.nome if atleta.campus else "Sem Campus Definido"
            campi_permitidos_str = ", ".join([c.nome for c in refeicao.campi_liberados.all()])
            return JsonResponse({
                'success': False,
                'message': f'REFEIÇÃO NÃO LIBERADA! O campus do atleta ({campus_atleta_nome}) não tem permissão para o {refeicao.get_tipo_display()}. Campi autorizados: {campi_permitidos_str}.',
                'atleta': {
                    'nome': atleta.nome_completo,
                    'campus': campus_atleta_nome,
                    'matricula': atleta.matricula,
                    'delegacao': get_delegacao_nome_atleta(atleta),
                }
            }, status=403)

        # VALIDAÇÃO 2: Garantir que permite apenas 1 refeição por tipo por dia por atleta
        registro_existente = RegistroRefeicao.objects.filter(refeicao=refeicao, atleta=atleta).first()
        if registro_existente:
            hora_retirada = timezone.localtime(registro_existente.data_retirada).strftime('%H:%M:%S')
            return JsonResponse({
                'success': False,
                'already_claimed': True,
                'message': f'ATENÇÃO: O atleta {atleta.nome_completo} JÁ RETIROU o {refeicao.get_tipo_display()} hoje às {hora_retirada}!',
                'atleta': {
                    'nome': atleta.nome_completo,
                    'campus': atleta.campus.nome if atleta.campus else "Sem Campus",
                    'matricula': atleta.matricula,
                    'delegacao': get_delegacao_nome_atleta(atleta),
                    'hora_retirada': hora_retirada,
                }
            }, status=409)

        # REGISTRO DA RETIRADA DA REFEIÇÃO
        registro = RegistroRefeicao.objects.create(
            refeicao=refeicao,
            atleta=atleta,
            validado_por=request.user
        )

        hora_sucesso = timezone.localtime(registro.data_retirada).strftime('%H:%M:%S')
        delegacao_nome = get_delegacao_nome_atleta(atleta)

        return JsonResponse({
            'success': True,
            'message': f'Refeição de {atleta.nome_completo} registrada com sucesso!',
            'registro': {
                'id': registro.id,
                'hora': hora_sucesso,
            },
            'atleta': {
                'id': atleta.id,
                'nome': atleta.nome_completo,
                'cpf': atleta.cpf or "-",
                'matricula': atleta.matricula,
                'campus': atleta.campus.nome if atleta.campus else "Sem Campus",
                'delegacao': delegacao_nome,
                'tipo_atleta': atleta.get_tipo_atleta_display(),
            },
            'refeicao': {
                'tipo': refeicao.get_tipo_display(),
                'data': refeicao.data.strftime('%d/%m/%Y'),
            }
        })

    except Exception as exc:
        return JsonResponse({
            'success': False,
            'message': f'Erro ao processar o registro: {str(exc)}'
        }, status=500)


@comissao_required
def relatorio_refeicoes_view(request):
    """
    Exibe estatísticas detalhadas e relatórios de refeições servidas com filtros por Data, Campus e Tipo de Refeição.
    """
    hoje = timezone.localdate()
    data_filtro_str = request.GET.get('data', hoje.strftime('%Y-%m-%d'))
    campus_id = request.GET.get('campus', '')
    tipo_filtro = request.GET.get('tipo', '')

    try:
        data_filtro = timezone.datetime.strptime(data_filtro_str, '%Y-%m-%d').date()
    except ValueError:
        data_filtro = hoje

    registros = RegistroRefeicao.objects.filter(refeicao__data=data_filtro).select_related(
        'atleta', 'atleta__campus', 'atleta__cadastrado_por', 'refeicao', 'validado_por'
    )

    if campus_id and str(campus_id).isdigit():
        registros = registros.filter(atleta__campus_id=int(campus_id))

    if tipo_filtro and tipo_filtro in ['cafe', 'almoco', 'jantar']:
        registros = registros.filter(refeicao__tipo=tipo_filtro)

    total_cafe = registros.filter(refeicao__tipo='cafe').count()
    total_almoco = registros.filter(refeicao__tipo='almoco').count()
    total_jantar = registros.filter(refeicao__tipo='jantar').count()
    total_geral = registros.count()

    campi = Campus.objects.all().order_by('nome')

    context = {
        'data_filtro': data_filtro,
        'campus_filtro': str(campus_id) if campus_id else '',
        'tipo_filtro': tipo_filtro,
        'registros': registros,
        'campi': campi,
        'total_cafe': total_cafe,
        'total_almoco': total_almoco,
        'total_jantar': total_jantar,
        'total_geral': total_geral,
    }
    return render(request, 'refeicoes/relatorio.html', context)


@comissao_required
def exportar_relatorio_refeicoes_view(request):
    """
    Endpoint para exportar o relatório de refeições.
    Exibe o documento oficial formatado para impressão e conversão em PDF,
    com resumos totalizadores por tipo de refeição e classificação dos estudantes por Campus em listagem contínua.
    """
    hoje = timezone.localdate()
    data_filtro_str = request.GET.get('data', hoje.strftime('%Y-%m-%d'))
    campus_id = request.GET.get('campus', '')
    tipo_filtro = request.GET.get('tipo', '')

    try:
        data_filtro = timezone.datetime.strptime(data_filtro_str, '%Y-%m-%d').date()
    except ValueError:
        data_filtro = hoje

    registros = RegistroRefeicao.objects.filter(refeicao__data=data_filtro).select_related(
        'atleta', 'atleta__campus', 'atleta__cadastrado_por', 'refeicao', 'validado_por'
    ).order_by('atleta__campus__nome', 'data_retirada')

    if campus_id and str(campus_id).isdigit():
        registros = registros.filter(atleta__campus_id=int(campus_id))

    if tipo_filtro and tipo_filtro in ['cafe', 'almoco', 'jantar']:
        registros = registros.filter(refeicao__tipo=tipo_filtro)

    total_cafe = registros.filter(refeicao__tipo='cafe').count()
    total_almoco = registros.filter(refeicao__tipo='almoco').count()
    total_jantar = registros.filter(refeicao__tipo='jantar').count()
    total_geral = registros.count()

    # Formato PRINT (Relatório HTML próprio para impressão e exportação em PDF)
    registros_agrupados = {}
    for r in registros:
        campus_obj = r.atleta.campus if r.atleta else None
        campus_nome = campus_obj.nome if campus_obj else 'Sem Campus Definido'
        if campus_nome not in registros_agrupados:
            registros_agrupados[campus_nome] = []
        
        delegacao_nome = get_delegacao_nome_atleta(r.atleta)
        registros_agrupados[campus_nome].append({
            'registro': r,
            'delegacao': delegacao_nome,
        })

    exibir_matricula = request.GET.get('exibir_matricula', '1') != '0'
    exibir_cpf = request.GET.get('exibir_cpf', '1') != '0'
    exibir_refeicao = request.GET.get('exibir_refeicao', '1') != '0'
    exibir_horario = request.GET.get('exibir_horario', '1') != '0'

    campus_filtro_obj = Campus.objects.filter(id=int(campus_id)).first() if campus_id and str(campus_id).isdigit() else None

    context = {
        'data_filtro': data_filtro,
        'data_emissao': timezone.now(),
        'gerado_por': request.user,
        'campus_filtro_obj': campus_filtro_obj,
        'tipo_filtro': tipo_filtro,
        'total_cafe': total_cafe,
        'total_almoco': total_almoco,
        'total_jantar': total_jantar,
        'total_geral': total_geral,
        'registros_agrupados': registros_agrupados,
        'exibir_matricula': exibir_matricula,
        'exibir_cpf': exibir_cpf,
        'exibir_refeicao': exibir_refeicao,
        'exibir_horario': exibir_horario,
    }
    return render(request, 'refeicoes/relatorio_print.html', context)
