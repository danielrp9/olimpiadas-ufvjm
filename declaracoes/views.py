import os
import json
from pathlib import Path

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse, HttpResponse, FileResponse, Http404
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db.models import Count, Q
from django.contrib.auth import get_user_model

from core.models import Atleta, Campus
from .models import MembroComissao, HistoricoEmissao
from .forms import MembroComissaoForm
from .services import (
    gerar_pdf_declaracao_bytes,
    iniciar_geracao_assincrona,
    get_task_progress,
    formatar_data_atual_ptbr
)

User = get_user_model()


def _is_comissao_or_admin(user):
    return user.is_authenticated and (getattr(user, 'is_comissao', False) or user.is_staff or user.is_superuser)


def _garantir_membros_iniciais_comissao():
    """
    Inicializa membros da comissão caso a tabela esteja vazia, aproveitando
    os usuários existentes no sistema e garantindo o modelo Daniel Rodrigues Pereira.
    """
    if MembroComissao.objects.count() == 0:
        # 1. Procura por Daniel Rodrigues Pereira no sistema ou cria
        user_daniel = User.objects.filter(nome_completo__icontains="Daniel Rodrigues").first()
        atleta_daniel = Atleta.objects.filter(nome_completo__icontains="Daniel Rodrigues").first()
        mat_daniel = atleta_daniel.matricula if atleta_daniel else "20212016010"
        
        MembroComissao.objects.create(
            nome_completo="Daniel Rodrigues Pereira",
            matricula=mat_daniel or "20212016010",
            cargo="Organizador",
            email=user_daniel.email if user_daniel else "daniel.pereira@ufvjm.edu.br",
            user=user_daniel,
            ativo=True
        )

        # 2. Puxa outros usuários com role COMISSAO que possuam nome
        users_comissao = User.objects.filter(role='COMISSAO')
        for u in users_comissao:
            if u.nome_completo and "Daniel" not in u.nome_completo:
                # Procura se tem matrícula como atleta
                mat = None
                atleta = Atleta.objects.filter(email=u.email).first()
                if atleta:
                    mat = atleta.matricula
                elif u.cpf:
                    mat = u.cpf

                MembroComissao.objects.get_or_create(
                    nome_completo=u.nome_completo,
                    defaults={
                        'matricula': mat,
                        'cargo': 'Organizador',
                        'email': u.email,
                        'user': u,
                        'ativo': True
                    }
                )


@user_passes_test(_is_comissao_or_admin)
def declaracoes_index_view(request):
    """
    Página principal do módulo independente de Emissão de Declarações.
    Permite parametrizar horas, período, campis e gerar declarações para atletas e comissão.
    """
    _garantir_membros_iniciais_comissao()

    # Todos os Campi disponíveis
    campis = Campus.objects.all().order_by('nome')
    
    # Atletas Deferidos
    atletas_deferidos = Atleta.objects.filter(status_avaliacao='deferido').select_related('campus', 'cadastrado_por').order_by('nome_completo')
    
    # Membros da Comissão
    membros_comissao = MembroComissao.objects.all().order_by('nome_completo')

    # Histórico de emissões recentes
    historicos = HistoricoEmissao.objects.all()[:8]

    # Valores padrão de formulário
    valores_padrao = {
        'horas_atleta': 60,
        'horas_comissao': 100,
        'periodo': "27 de setembro a 25 de outubro de 2025",
        'cidade_data': formatar_data_atual_ptbr(),
        'projeto_texto': "projeto de extensão “Olimpíadas Universitárias UFVJM 2025: Esporte, Cultura e Inclusão”, registro PROEXC/UFVJM 202203001466",
    }

    form_membro = MembroComissaoForm()

    context = {
        'campis': campis,
        'atletas_deferidos': atletas_deferidos,
        'total_atletas_deferidos': atletas_deferidos.count(),
        'membros_comissao': membros_comissao,
        'total_comissao': membros_comissao.filter(ativo=True).count(),
        'historicos': historicos,
        'valores_padrao': valores_padrao,
        'form_membro': form_membro,
    }
    return render(request, 'declaracoes/index.html', context)


@user_passes_test(_is_comissao_or_admin)
def previa_declaracao_view(request):
    """
    Gera uma prévia em tempo real de 1 PDF para o usuário visualizar o layout e formatação.
    """
    tipo = request.GET.get('tipo', 'atleta')
    horas = request.GET.get('horas', 100)
    periodo = request.GET.get('periodo', '27 de setembro a 25 de outubro de 2025')
    cidade_data = request.GET.get('cidade_data', formatar_data_atual_ptbr())
    projeto_texto = request.GET.get(
        'projeto_texto',
        "projeto de extensão “Olimpíadas Universitárias UFVJM 2025: Esporte, Cultura e Inclusão”, registro PROEXC/UFVJM 202203001466"
    )
    item_id = request.GET.get('id')

    if tipo == 'comissao':
        papel = "Organizador"
        membro = None
        if item_id:
            membro = MembroComissao.objects.filter(id=item_id).first()
        if not membro:
            membro = MembroComissao.objects.filter(ativo=True).first()

        nome = membro.nome_completo if membro else "Daniel Rodrigues Pereira"
        matricula = membro.matricula if membro else "20212016010"
        papel = membro.cargo if membro and membro.cargo else "Organizador"
    else:
        papel = "Atleta"
        atleta = None
        if item_id:
            atleta = Atleta.objects.filter(id=item_id, status_avaliacao='deferido').first()
        if not atleta:
            atleta = Atleta.objects.filter(status_avaliacao='deferido').first()

        nome = atleta.nome_completo if atleta else "Daniel Rodrigues Pereira"
        matricula = atleta.matricula if atleta else "20212016010"

    try:
        pdf_bytes = gerar_pdf_declaracao_bytes(
            nome=nome,
            matricula=matricula,
            papel=papel,
            projeto_texto=projeto_texto,
            periodo=periodo,
            horas=horas,
            cidade_data=cidade_data
        )
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="Previa_Declaracao_{tipo}.pdf"'
        return response
    except Exception as e:
        return HttpResponse(f"Erro ao gerar prévia: {str(e)}", status=500)


@user_passes_test(_is_comissao_or_admin)
@require_POST
def iniciar_geracao_view(request):
    """
    Recebe os parâmetros via JSON/POST, valida e inicia a geração assíncrona com ID de acompanhamento.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = request.POST

    tipo = data.get('tipo', 'atleta')
    horas = int(data.get('horas', 100))
    periodo = data.get('periodo', '27 de setembro a 25 de outubro de 2025')
    cidade_data = data.get('cidade_data', formatar_data_atual_ptbr())
    projeto_texto = data.get(
        'projeto_texto',
        "projeto de extensão “Olimpíadas Universitárias UFVJM 2025: Esporte, Cultura e Inclusão”, registro PROEXC/UFVJM 202203001466"
    )
    campis_ids = data.get('campis', [])
    selecionados_ids = data.get('selecionados', [])

    try:
        task_id = iniciar_geracao_assincrona(
            tipo=tipo,
            selecionados_ids=selecionados_ids,
            horas=horas,
            periodo=periodo,
            cidade_data=cidade_data,
            projeto_texto=projeto_texto,
            campis_ids=campis_ids,
            solicitado_por=request.user
        )
        return JsonResponse({
            'success': True,
            'task_id': task_id,
            'message': 'Geração iniciada com sucesso.'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@user_passes_test(_is_comissao_or_admin)
def progresso_geracao_view(request, task_id):
    """
    Retorna o status atual e a porcentagem de conclusão da geração em andamento.
    """
    info = get_task_progress(task_id)
    if not info:
        return JsonResponse({
            'status': 'nao_encontrado',
            'porcentagem': 0,
            'mensagem': 'Tarefa não encontrada.'
        }, status=404)

    return JsonResponse(info)


@user_passes_test(_is_comissao_or_admin)
def download_zip_view(request, task_id):
    """
    Permite ao usuário baixar o arquivo ZIP contendo todas as declarações individuais.
    """
    info = get_task_progress(task_id)
    if not info or info.get('status') != 'concluido':
        raise Http404("Arquivo de declarações não encontrado ou geração ainda não concluída.")

    zip_path = info.get('zip_path')
    if not zip_path or not os.path.exists(zip_path):
        raise Http404("O arquivo compactado não foi encontrado no servidor.")

    zip_filename = info.get('zip_filename', 'Declaracoes.zip')
    return FileResponse(
        open(zip_path, 'rb'),
        as_attachment=True,
        filename=zip_filename,
        content_type='application/zip'
    )


@user_passes_test(_is_comissao_or_admin)
@require_POST
def salvar_membro_comissao_view(request):
    """
    Adiciona ou edita um membro da comissão via formulário/AJAX.
    """
    membro_id = request.POST.get('membro_id')
    instance = None
    if membro_id:
        instance = get_object_or_404(MembroComissao, id=membro_id)

    form = MembroComissaoForm(request.POST, instance=instance)
    if form.is_valid():
        membro = form.save()
        messages.success(request, f"Membro {membro.nome_completo} salvo com sucesso!")
        return redirect('declaracoes_index')
    else:
        messages.error(request, "Erro ao salvar membro da comissão. Verifique os dados.")
        return redirect('declaracoes_index')


@user_passes_test(_is_comissao_or_admin)
@require_POST
def excluir_membro_comissao_view(request, membro_id):
    """
    Exclui um membro da comissão organizadora.
    """
    membro = get_object_or_404(MembroComissao, id=membro_id)
    nome = membro.nome_completo
    membro.delete()
    messages.success(request, f"Membro {nome} removido da lista.")
    return redirect('declaracoes_index')


@user_passes_test(_is_comissao_or_admin)
def sincronizar_comissao_view(request):
    """
    Varre os usuários da comissão no sistema e adiciona os que faltam na lista.
    """
    users_comissao = User.objects.filter(role='COMISSAO')
    adicionados = 0
    for u in users_comissao:
        if u.nome_completo:
            obj, created = MembroComissao.objects.get_or_create(
                nome_completo=u.nome_completo,
                defaults={
                    'matricula': u.cpf,
                    'cargo': 'Organizador',
                    'email': u.email,
                    'user': u,
                    'ativo': True
                }
            )
            if created:
                adicionados += 1

    messages.success(request, f"Sincronização concluída! {adicionados} novo(s) membro(s) adicionado(s).")
    return redirect('declaracoes_index')
