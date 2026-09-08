import io
import os
import re
import uuid
import time
import zipfile
import threading
from pathlib import Path

from django.conf import settings
from django.utils import timezone

try:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
except ImportError:
    PdfReader = None
    PdfWriter = None

from core.models import Atleta, Campus
from .models import MembroComissao, HistoricoEmissao


# Armazenamento em memória para o progresso em tempo real das tarefas
_TASK_PROGRESS = {}
_TASK_LOCK = threading.Lock()


def get_task_progress(task_id):
    with _TASK_LOCK:
        return _TASK_PROGRESS.get(task_id)


def update_task_progress(task_id, **kwargs):
    with _TASK_LOCK:
        if task_id not in _TASK_PROGRESS:
            _TASK_PROGRESS[task_id] = {}
        _TASK_PROGRESS[task_id].update(kwargs)


def get_template_pdf_path():
    """
    Retorna o caminho para o arquivo base oficial da declaração.
    """
    caminho_padrao = Path(settings.BASE_DIR) / 'declaracoes' / 'assets' / 'DECLARAÇÃO OFICIAL.pdf'
    if caminho_padrao.exists():
        return str(caminho_padrao)
    
    # Fallback na raiz do projeto
    caminho_raiz = Path(settings.BASE_DIR) / 'DECLARAÇÃO OFICIAL.pdf'
    if caminho_raiz.exists():
        return str(caminho_raiz)
        
    raise FileNotFoundError("O arquivo modelo 'DECLARAÇÃO OFICIAL.pdf' não foi encontrado.")


def formatar_data_atual_ptbr():
    """
    Gera a data de hoje por extenso em português.
    Ex: Diamantina, 8 de setembro de 2026
    """
    meses = [
        "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
    ]
    hoje = timezone.now().date()
    mes_nome = meses[hoje.month]
    return f"Diamantina, {hoje.day} de {mes_nome} de {hoje.year}"


def sanitizar_nome_arquivo(nome):
    """
    Remove caracteres inválidos para nomes de arquivos mantendo letras acentuadas e espaços.
    """
    nome_limpo = re.sub(r'[\\/*?:"<>|]', '', nome).strip()
    return nome_limpo if nome_limpo else "declaracao"


def gerar_pdf_declaracao_bytes(
    nome,
    matricula=None,
    papel="Atleta",
    projeto_texto=None,
    periodo=None,
    horas=100,
    cidade_data=None,
    template_path=None
):
    """
    Gera uma declaração individual mesclando o texto dinâmico sobre o template oficial PDF.
    Retorna os bytes do PDF gerado.
    """
    if PdfReader is None:
        raise ImportError(
            "As bibliotecas 'pypdf' e 'reportlab' são obrigatórias para emitir declarações. "
            "Por favor, execute: pip install -r requirements.txt"
        )

    if template_path is None:
        template_path = get_template_pdf_path()

    if not projeto_texto:
        projeto_texto = (
            "projeto de extensão “Olimpíadas Universitárias UFVJM 2025: Esporte, "
            "Cultura e Inclusão”, registro PROEXC/UFVJM 202203001466"
        )
    
    if not periodo:
        periodo = "27 de setembro a 25 de outubro de 2025"

    if not cidade_data:
        cidade_data = formatar_data_atual_ptbr()

    # Formata a matrícula se existir
    mat_str = ""
    if matricula and str(matricula).strip() and str(matricula).strip().lower() != 'none':
        mat_str = f"matrícula {str(matricula).strip()}, "

    # Negrita o título do projeto caso ainda não tenha tags HTML
    if "“Olimpíadas Universitárias" in projeto_texto and "<b>" not in projeto_texto:
        projeto_formatado = projeto_texto.replace(
            "“Olimpíadas Universitárias UFVJM 2025: Esporte, Cultura e Inclusão”",
            "<b>“Olimpíadas Universitárias UFVJM 2025: Esporte, Cultura e Inclusão”</b>"
        )
    else:
        projeto_formatado = projeto_texto

    # Monta o texto completo da declaração
    conteudo_declaracao = (
        f"Declaramos para os devidos fins que {nome}, {mat_str}"
        f"participou como {papel} do {projeto_formatado}, "
        f"realizado no período de {periodo}, "
        f"com carga horária total de {horas} horas."
    )

    # Cria o canvas de sobreposição (mesmas dimensões A4 do template: 596 x 842 pt)
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(596, 842))

    # 1. Título "DECLARAÇÃO"
    can.setFont('Helvetica-Bold', 14)
    can.drawCentredString(298.0, 600, 'DECLARAÇÃO')

    # 2. Parágrafo Justificado
    style = ParagraphStyle(
        'DeclaracaoBody',
        fontName='Helvetica',
        fontSize=13.5,
        leading=23,
        alignment=TA_JUSTIFY,
    )
    p = Paragraph(conteudo_declaracao, style)
    largura_paragrafo = 440
    w, h = p.wrap(largura_paragrafo, 350)
    pos_x = (596 - largura_paragrafo) / 2.0  # 78 pt
    pos_y = 545 - h
    p.drawOn(can, pos_x, pos_y)

    # 3. Data e Local Centralizado (abaixo do parágrafo e acima da linha de assinatura)
    data_y = max(pos_y - 55, 340)
    can.setFont('Helvetica', 13.5)
    can.drawCentredString(298.0, data_y, cidade_data)

    can.save()
    packet.seek(0)

    # Mescla o template com a camada de texto gerada
    template_pdf = PdfReader(template_path)
    overlay_pdf = PdfReader(packet)

    writer = PdfWriter()
    page = template_pdf.pages[0]
    page.merge_page(overlay_pdf.pages[0])
    writer.add_page(page)

    output_stream = io.BytesIO()
    writer.write(output_stream)
    return output_stream.getvalue()


def executar_geracao_lote_thread(
    task_id,
    itens,
    papel,
    tipo,
    horas,
    periodo,
    cidade_data,
    projeto_texto,
    solicitado_por_id=None
):
    """
    Processo em segundo plano que gera cada declaração em PDF, atualiza a porcentagem
    de progresso e empacota tudo num arquivo .ZIP para download.
    """
    total = len(itens)
    update_task_progress(
        task_id,
        status='processando',
        total=total,
        atual=0,
        porcentagem=0,
        mensagem=f"Iniciando a geração de {total} declarações..."
    )

    try:
        template_path = get_template_pdf_path()
        zip_buffer = io.BytesIO()
        nomes_utilizados = {}

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for idx, item in enumerate(itens):
                nome = item.get('nome', 'Sem Nome').strip()
                matricula = item.get('matricula', '').strip()
                
                # Nome de arquivo seguro e com desambiguação
                nome_base = sanitizar_nome_arquivo(nome)
                if nome_base in nomes_utilizados:
                    nomes_utilizados[nome_base] += 1
                    nome_arquivo = f"{nome_base} ({nomes_utilizados[nome_base]}).pdf"
                else:
                    nomes_utilizados[nome_base] = 1
                    nome_arquivo = f"{nome_base}.pdf"

                # Atualiza progresso antes/durante
                update_task_progress(
                    task_id,
                    atual=idx + 1,
                    porcentagem=int(((idx + 1) / total) * 100),
                    mensagem=f"Gerando ({idx + 1}/{total}): {nome}...",
                    individuo_atual=nome
                )

                # Gera bytes do PDF individual
                pdf_bytes = gerar_pdf_declaracao_bytes(
                    nome=nome,
                    matricula=matricula,
                    papel=papel,
                    projeto_texto=projeto_texto,
                    periodo=periodo,
                    horas=horas,
                    cidade_data=cidade_data,
                    template_path=template_path
                )

                # Grava no ZIP
                zip_file.writestr(nome_arquivo, pdf_bytes)

                # Pequena pausa para permitir renderização suave da barra de progresso no frontend
                time.sleep(0.03)

        # Salva o arquivo ZIP gerado
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        sufixo_tipo = "Atletas" if tipo == 'atleta' else "Comissao"
        zip_filename = f"Declaracoes_{sufixo_tipo}_{timestamp}.zip"
        
        diretorio_saida = Path(settings.MEDIA_ROOT) / 'declaracoes'
        diretorio_saida.mkdir(parents=True, exist_ok=True)
        zip_filepath = diretorio_saida / f"{task_id}_{zip_filename}"

        with open(zip_filepath, 'wb') as f:
            f.write(zip_buffer.getvalue())

        # Registra no histórico do banco de dados
        try:
            HistoricoEmissao.objects.create(
                tipo=tipo,
                total_documentos=total,
                carga_horaria=horas,
                periodo=periodo,
                cidade_data=cidade_data,
                solicitado_por_id=solicitado_por_id
            )
        except Exception:
            pass

        update_task_progress(
            task_id,
            status='concluido',
            atual=total,
            porcentagem=100,
            mensagem=f"Sucesso! {total} declarações geradas com sucesso.",
            zip_path=str(zip_filepath),
            zip_filename=zip_filename,
            total=total
        )

    except Exception as e:
        update_task_progress(
            task_id,
            status='erro',
            mensagem=f"Ocorreu um erro durante a geração: {str(e)}"
        )


def iniciar_geracao_assincrona(
    tipo,
    selecionados_ids,
    horas,
    periodo,
    cidade_data,
    projeto_texto=None,
    campis_ids=None,
    solicitado_por=None
):
    """
    Prepara a lista de indivíduos e inicia o processamento assíncrono.
    Retorna o task_id único para acompanhamento.
    """
    task_id = str(uuid.uuid4())
    itens = []
    papel = "Atleta" if tipo == 'atleta' else "Organizador"

    if tipo == 'atleta':
        qs = Atleta.objects.filter(status_avaliacao='deferido')
        
        # Filtro de Campi se fornecido
        if campis_ids:
            # Tratamento especial caso inclua "sem campus"
            inclui_sem_campus = 'sem_campus' in campis_ids or None in campis_ids or '0' in campis_ids
            val_ids = [c for c in campis_ids if c not in ('sem_campus', '0', None)]
            
            from django.db.models import Q
            q_filter = Q(campus_id__in=val_ids)
            if inclui_sem_campus:
                q_filter |= Q(campus__isnull=True)
            qs = qs.filter(q_filter)

        # Filtro de IDs específicos selecionados
        if selecionados_ids:
            qs = qs.filter(id__in=selecionados_ids)

        for atleta in qs.order_by('nome_completo'):
            itens.append({
                'id': atleta.id,
                'nome': atleta.nome_completo,
                'matricula': atleta.matricula,
            })
    else:
        # Comissão Organizadora
        qs = MembroComissao.objects.filter(ativo=True)
        if selecionados_ids:
            qs = qs.filter(id__in=selecionados_ids)
            
        for membro in qs.order_by('nome_completo'):
            itens.append({
                'id': membro.id,
                'nome': membro.nome_completo,
                'matricula': membro.matricula or '',
                'cargo': membro.cargo or 'Organizador'
            })

    if not itens:
        raise ValueError("Nenhum indivíduo elegível encontrado para emissão.")

    update_task_progress(
        task_id,
        status='iniciando',
        porcentagem=0,
        atual=0,
        total=len(itens),
        mensagem="Iniciando processamento..."
    )

    thread = threading.Thread(
        target=executar_geracao_lote_thread,
        args=(
            task_id,
            itens,
            papel,
            tipo,
            horas,
            periodo,
            cidade_data,
            projeto_texto,
            solicitado_por.id if solicitado_por else None
        ),
        daemon=True
    )
    thread.start()

    return task_id
