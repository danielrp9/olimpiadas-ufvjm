import json
from django.http import JsonResponse
from django.views import View
from django.contrib.auth import login as auth_login, logout as auth_logout, get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from .models import Campus, Atleta, Modalidade, Jogo, PreSumula, PreSumulaAtleta, Inscricao, InscricaoModalidade, Notificacao
from users.models import ComissaoWhitelist

User = get_user_model()

def get_campus_instance(value):
    if not value:
        return None
    val_str = str(value).strip()
    if not val_str:
        return None
    if val_str.isdigit():
        campus = Campus.objects.filter(pk=int(val_str)).first()
        if campus:
            return campus
    campus = Campus.objects.filter(nome__iexact=val_str).first()
    if not campus and not val_str.isdigit():
        campus = Campus.objects.create(nome=val_str)
    return campus

def user_to_dict(user):
    if not user:
        return None
    delegacao = user.delegacao_ativa
    return {
        'id': user.id,
        'email': user.email,
        'nome_completo': user.nome_completo,
        'foto_url': user.foto_url,
        'role': user.role,
        'parent_delegate_id': user.parent_delegate_id,
        'perfil_completo': user.perfil_completo,
        'cpf': user.cpf or (user.parent_delegate.cpf if user.parent_delegate else None),
        'nome_delegacao': delegacao.nome_delegacao,
        'status_delegacao': delegacao.status_delegacao,
        'justificativa_delegacao': delegacao.justificativa_delegacao,
        'is_comissao': user.is_comissao,
        'is_superuser': user.is_superuser
    }

def atleta_to_dict(atleta):
    return {
        'id': atleta.id,
        'nome_completo': atleta.nome_completo,
        'email': atleta.email,
        'cpf': atleta.cpf,
        'matricula': atleta.matricula,
        'curso': atleta.curso,
        'campus': atleta.campus.nome if atleta.campus else '',
        'genero': atleta.genero,
        'genero_display': atleta.get_genero_display(),
        'tipo_atleta': atleta.tipo_atleta,
        'tipo_atleta_display': atleta.get_tipo_atleta_display(),
        'link_documento': atleta.link_documento,
        'is_egresso': atleta.is_egresso,
        'link_documento_egresso': atleta.link_documento_egresso,
        'em_conformidade': atleta.em_conformidade,
        'justificativa_inconformidade': atleta.justificativa_inconformidade,
        'permite_correcao': atleta.permite_correcao,
        'link_correcao': atleta.link_correcao,
        'cadastrado_por_id': atleta.cadastrado_por_id,
        'status_avaliacao': atleta.status_avaliacao,
        'status_avaliacao_display': atleta.get_status_avaliacao_display()
    }

def modalidade_to_dict(modalidade):
    return {
        'id': modalidade.id,
        'nome': modalidade.nome,
        'genero': modalidade.genero,
        'genero_display': modalidade.get_genero_display(),
        'limite_minimo_jogadores': modalidade.limite_minimo_jogadores,
        'limite_maximo_jogadores': modalidade.limite_maximo_jogadores,
        'inscricoes_abertas': modalidade.inscricoes_abertas,
        'data_publicacao': None
    }

def jogo_to_dict(jogo):
    return {
        'id': jogo.id,
        'modalidade': modalidade_to_dict(jogo.modalidade),
        'data_jogo': jogo.data_jogo.isoformat(),
        'horario_jogo': jogo.horario_jogo.strftime('%H:%M') if jogo.horario_jogo else None,
        'time_a': {
            'id': jogo.time_a.id,
            'nome_delegacao': jogo.time_a.nome_delegacao or jogo.time_a.email,
            'nome_completo': jogo.time_a.nome_completo
        },
        'time_b': {
            'id': jogo.time_b.id,
            'nome_delegacao': jogo.time_b.nome_delegacao or jogo.time_b.email,
            'nome_completo': jogo.time_b.nome_completo
        },
        'local': jogo.local,
        'arbitro': jogo.arbitro,
        'finalizado': jogo.finalizado,
        'is_finalizado_por_wo': jogo.is_finalizado_por_wo
    }


# --- AUTHENTICATION ---

class APIAuthMeView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return JsonResponse({'authenticated': True, 'user': user_to_dict(request.user)})
        return JsonResponse({'authenticated': False, 'user': None})

@method_decorator(csrf_exempt, name='dispatch')
class APIAuthLoginView(View):
    """
    Endpoint de login facilitado para desenvolvimento.
    Recebe um email e faz login (sem senha) se o usuário existir.
    """
    def post(self, request):
        try:
            data = json.loads(request.body)
            email = data.get('email', '').strip().lower()
            if not email:
                return JsonResponse({'error': 'E-mail é obrigatório.'}, status=400)
            
            user = User.objects.filter(email__iexact=email).first()
            if not user:
                # Se não existir, em dev podemos criar para facilitar o teste
                is_in_whitelist = ComissaoWhitelist.objects.filter(email__iexact=email).exists()
                role = 'COMISSAO' if is_in_whitelist else 'REPRESENTANTE'
                
                user = User.objects.create_user(
                    email=email,
                    nome_completo=email.split('@')[0].capitalize(),
                    role=role
                )
            
            auth_login(request, user)
            return JsonResponse({'success': True, 'user': user_to_dict(user)})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class APIAuthLogoutView(View):
    def post(self, request):
        auth_logout(request)
        return JsonResponse({'success': True})

@method_decorator(csrf_exempt, name='dispatch')
class APIAuthCompleteProfileView(View):
    def post(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
        
        try:
            data = json.loads(request.body)
            cpf = data.get('cpf', '').strip()
            nome_delegacao = data.get('nome_delegacao', '').strip()
            
            if not cpf or not nome_delegacao:
                return JsonResponse({'error': 'CPF e Nome da Delegação são obrigatórios.'}, status=400)
            
            user = request.user
            user.cpf = cpf
            user.nome_delegacao = nome_delegacao
            user.save() # isso também atualiza perfil_completo = True se for representante
            
            return JsonResponse({'success': True, 'user': user_to_dict(user)})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


# --- DASHBOARD ---

class APIDashboardView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
        
        user = request.user
        if user.is_comissao:
            total_atletas_global = Atleta.objects.count()
            total_usuarios = User.objects.filter(role='REPRESENTANTE', inscricao__isnull=False).count()
            total_presumulas_global = PreSumula.objects.count()
            total_modalidades = Modalidade.objects.count()
            
            return JsonResponse({
                'is_admin': True,
                'total_atletas_global': total_atletas_global,
                'total_usuarios': total_usuarios,
                'total_presumulas_global': total_presumulas_global,
                'total_modalidades': total_modalidades
            })
        
        delegacao = user.delegacao_ativa
        total_atletas = Atleta.objects.filter(cadastrado_por=delegacao).count()
        
        minhas_presumulas = PreSumula.objects.filter(representante=delegacao).order_by('-jogo__data_jogo')
        presumulas_data = []
        for ps in minhas_presumulas:
            presumulas_data.append({
                'id': ps.id,
                'jogo_id': ps.jogo_id,
                'jogo_str': str(ps.jogo),
                'data_jogo': ps.jogo.data_jogo.isoformat()
            })
            
        modalidades_abertas = Modalidade.objects.filter(inscricoes_abertas=True)
        modalidades_data = [modalidade_to_dict(m) for m in modalidades_abertas]
        
        inscricao = getattr(delegacao, 'inscricao', None)
        inscricao_data = None
        if inscricao:
            inscricao_data = {
                'id': inscricao.id,
                'status': inscricao.status,
                'status_display': inscricao.get_status_display(),
                'justificativa': inscricao.justificativa,
                'data_envio': inscricao.data_envio.isoformat()
            }
            
        return JsonResponse({
            'is_admin': False,
            'total_atletas': total_atletas,
            'minhas_presumulas': presumulas_data,
            'modalidades_abertas': modalidades_data,
            'inscricao': inscricao_data
        })


# --- ATLETAS ---

@method_decorator(csrf_exempt, name='dispatch')
class APIAtletasView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
        
        # Se for comissão, ele pode opcionalmente ver todos
        if request.user.is_comissao:
            atletas = Atleta.objects.all().order_by('nome_completo')
        else:
            atletas = Atleta.objects.filter(cadastrado_por=request.user.delegacao_ativa).order_by('nome_completo')
            
        return JsonResponse({'atletas': [atleta_to_dict(a) for a in atletas]})
        
    def post(self, request):
        """ Cadastro de Atletas (único ou lote) """
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
        if request.user.is_comissao:
            return JsonResponse({'error': 'Comissão não pode cadastrar atletas'}, status=403)
            
        try:
            data = json.loads(request.body)
            # Pode vir uma lista ou objeto único
            is_bulk = isinstance(data, list)
            items = data if is_bulk else [data]
            
            atletas_criados = []
            for item in items:
                nome = item.get('nome_completo', '').strip()
                if not nome:
                    continue
                    
                atleta = Atleta.objects.create(
                    nome_completo=nome,
                    cpf=item.get('cpf', '').strip(),
                    email=item.get('email', '').strip(),
                    matricula=item.get('matricula', '').strip(),
                    curso=item.get('curso', '').strip(),
                    campus=get_campus_instance(item.get('campus')),
                    genero=item.get('genero', 'M'),
                    tipo_atleta=item.get('tipo_atleta', 'estudante'),
                    is_egresso=bool(item.get('is_egresso', False)),
                    link_documento_egresso=item.get('link_documento_egresso', '').strip(),
                    link_documento=item.get('link_documento', '').strip(),
                    cadastrado_por=request.user.delegacao_ativa
                )
                atletas_criados.append(atleta_to_dict(atleta))
                
            return JsonResponse({'success': True, 'atletas': atletas_criados})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

@method_decorator(csrf_exempt, name='dispatch')
class APIAtletaDetailView(View):
    def put(self, request, pk):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        atleta = get_object_or_404(Atleta, pk=pk)
        if not request.user.is_comissao and atleta.cadastrado_por != request.user.delegacao_ativa:
            return JsonResponse({'error': 'Não autorizado'}, status=403)
            
        try:
            data = json.loads(request.body)
            # Se for representante, atualiza dados normais ou link de correção
            if not request.user.is_comissao:
                atleta.nome_completo = data.get('nome_completo', atleta.nome_completo)
                atleta.cpf = data.get('cpf', atleta.cpf)
                atleta.email = data.get('email', atleta.email)
                atleta.matricula = data.get('matricula', atleta.matricula)
                atleta.curso = data.get('curso', atleta.curso)
                atleta.campus = get_campus_instance(data.get('campus')) if 'campus' in data else atleta.campus
                atleta.genero = data.get('genero', atleta.genero)
                atleta.tipo_atleta = data.get('tipo_atleta', atleta.tipo_atleta)
                atleta.is_egresso = bool(data.get('is_egresso', atleta.is_egresso))
                atleta.link_documento_egresso = data.get('link_documento_egresso', atleta.link_documento_egresso)
                atleta.link_documento = data.get('link_documento', atleta.link_documento)
                
                # Se estiver enviando uma correção
                if data.get('link_correcao') and atleta.permite_correcao:
                    atleta.link_correcao = data.get('link_correcao')
            else:
                # Comissão editando
                atleta.nome_completo = data.get('nome_completo', atleta.nome_completo)
                atleta.cpf = data.get('cpf', atleta.cpf)
                atleta.email = data.get('email', atleta.email)
                atleta.matricula = data.get('matricula', atleta.matricula)
                atleta.curso = data.get('curso', atleta.curso)
                atleta.campus = get_campus_instance(data.get('campus')) if 'campus' in data else atleta.campus
                atleta.genero = data.get('genero', atleta.genero)
                atleta.tipo_atleta = data.get('tipo_atleta', atleta.tipo_atleta)
                atleta.is_egresso = bool(data.get('is_egresso', atleta.is_egresso))
                atleta.link_documento_egresso = data.get('link_documento_egresso', atleta.link_documento_egresso)
                atleta.link_documento = data.get('link_documento', atleta.link_documento)
                
            atleta.save()
            return JsonResponse({'success': True, 'atleta': atleta_to_dict(atleta)})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
            
    def delete(self, request, pk):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        atleta = get_object_or_404(Atleta, pk=pk)
        if not request.user.is_comissao and atleta.cadastrado_por != request.user.delegacao_ativa:
            return JsonResponse({'error': 'Não autorizado'}, status=403)
            
        atleta.delete()
        return JsonResponse({'success': True})

@method_decorator(csrf_exempt, name='dispatch')
class APIAtletaEnviarCorrecaoView(View):
    def post(self, request, pk):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
        atleta = get_object_or_404(Atleta, pk=pk, cadastrado_por=request.user.delegacao_ativa)
        if not atleta.permite_correcao:
            return JsonResponse({'error': 'Este atleta não está habilitado para correções.'}, status=400)
            
        try:
            data = json.loads(request.body)
            novo_link = data.get('link_correcao')
            if not novo_link:
                return JsonResponse({'error': 'Link de correção é obrigatório.'}, status=400)
                
            atleta.link_correcao = novo_link
            atleta.save()
            return JsonResponse({'success': True, 'atleta': atleta_to_dict(atleta)})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

@method_decorator(csrf_exempt, name='dispatch')
class APIAtletaResetConformidadeView(View):
    def post(self, request, pk):
        if not request.user.is_authenticated or not request.user.is_comissao:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        atleta = get_object_or_404(Atleta, pk=pk)
        atleta.em_conformidade = True
        atleta.justificativa_inconformidade = ""
        atleta.status_avaliacao = 'deferido'
        atleta.save()
        return JsonResponse({'success': True, 'atleta': atleta_to_dict(atleta)})

@method_decorator(csrf_exempt, name='dispatch')
class APIAtletaAvaliarView(View):
    def post(self, request, pk):
        if not request.user.is_authenticated or not request.user.is_comissao:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        atleta = get_object_or_404(Atleta, pk=pk)
        try:
            data = json.loads(request.body)
            status = data.get('status') # 'deferido' ou 'indeferido'
            justificativa = data.get('justificativa', '')
            permite_correcao = bool(data.get('permite_correcao', False))
            
            if status == 'deferido':
                atleta.em_conformidade = True
                atleta.justificativa_inconformidade = ''
                atleta.permite_correcao = False
                atleta.link_correcao = None
                atleta.status_avaliacao = 'deferido'
            elif status == 'indeferido':
                atleta.em_conformidade = False
                atleta.justificativa_inconformidade = justificativa
                atleta.permite_correcao = permite_correcao
                atleta.status_avaliacao = 'indeferido'
            else:
                return JsonResponse({'error': 'Status inválido. Deve ser deferido ou indeferido'}, status=400)
                
            atleta.save()
            return JsonResponse({'success': True, 'atleta': atleta_to_dict(atleta)})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


# --- MODALIDADES ---

@method_decorator(csrf_exempt, name='dispatch')
class APIModalidadesView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
        
        # Filtro de visibilidade igual à view clássica para representantes
        if request.user.is_comissao:
            modalidades = Modalidade.objects.all().order_by('nome')
        else:
            modalidades = Modalidade.objects.filter(inscricoes_abertas=True).order_by('nome')
            
        return JsonResponse({'modalidades': [modalidade_to_dict(m) for m in modalidades]})
        
    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_comissao:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        try:
            data = json.loads(request.body)
            nome = data.get('nome', '').strip()
            if not nome:
                return JsonResponse({'error': 'Nome é obrigatório.'}, status=400)
                
            modalidade = Modalidade.objects.create(
                nome=nome,
                genero=data.get('genero', 'M'),
                limite_minimo_jogadores=int(data.get('limite_minimo_jogadores', 1)),
                limite_maximo_jogadores=int(data.get('limite_maximo_jogadores', 20)),
                inscricoes_abertas=bool(data.get('inscricoes_abertas', True))
            )
            return JsonResponse({'success': True, 'modalidade': modalidade_to_dict(modalidade)})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

@method_decorator(csrf_exempt, name='dispatch')
class APIModalidadeDetailView(View):
    def put(self, request, pk):
        if not request.user.is_authenticated or not request.user.is_comissao:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        modalidade = get_object_or_404(Modalidade, pk=pk)
        try:
            data = json.loads(request.body)
            modalidade.nome = data.get('nome', modalidade.nome)
            modalidade.genero = data.get('genero', modalidade.genero)
            modalidade.limite_minimo_jogadores = int(data.get('limite_minimo_jogadores', modalidade.limite_minimo_jogadores))
            modalidade.limite_maximo_jogadores = int(data.get('limite_maximo_jogadores', modalidade.limite_maximo_jogadores))
            modalidade.inscricoes_abertas = bool(data.get('inscricoes_abertas', modalidade.inscricoes_abertas))
            modalidade.save()
            return JsonResponse({'success': True, 'modalidade': modalidade_to_dict(modalidade)})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
            
    def delete(self, request, pk):
        if not request.user.is_authenticated or not request.user.is_comissao:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        modalidade = get_object_or_404(Modalidade, pk=pk)
        modalidade.delete()
        return JsonResponse({'success': True})

@method_decorator(csrf_exempt, name='dispatch')
class APIModalidadeToggleView(View):
    def post(self, request, pk):
        if not request.user.is_authenticated or not request.user.is_comissao:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        modalidade = get_object_or_404(Modalidade, pk=pk)
        modalidade.inscricoes_abertas = not modalidade.inscricoes_abertas
        modalidade.save()
        return JsonResponse({'success': True, 'modalidade': modalidade_to_dict(modalidade)})


# --- JOGOS ---

@method_decorator(csrf_exempt, name='dispatch')
class APIJogosView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        # Comissão vê todos, Representante vê os relacionados à sua delegação
        if request.user.is_comissao:
            jogos = Jogo.objects.all().order_by('-data_jogo', '-horario_jogo')
        else:
            delegacao = request.user.delegacao_ativa
            jogos = Jogo.objects.filter(Q(time_a=delegacao) | Q(time_b=delegacao)).order_by('-data_jogo', '-horario_jogo')
            
        return JsonResponse({'jogos': [jogo_to_dict(j) for j in jogos]})

    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_comissao:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        try:
            data = json.loads(request.body)
            modalidade_id = data.get('modalidade_id')
            time_a_id = data.get('time_a_id')
            time_b_id = data.get('time_b_id')
            data_jogo = data.get('data_jogo')
            horario_jogo = data.get('horario_jogo')
            local = data.get('local')
            
            if not modalidade_id or not time_a_id or not time_b_id or not data_jogo:
                return JsonResponse({'error': 'Modalidade, Times A e B e Data do jogo são obrigatórios.'}, status=400)
                
            modalidade = get_object_or_404(Modalidade, pk=modalidade_id)
            time_a = get_object_or_404(User, pk=time_a_id, role='REPRESENTANTE')
            time_b = get_object_or_404(User, pk=time_b_id, role='REPRESENTANTE')
            
            jogo = Jogo.objects.create(
                modalidade=modalidade,
                time_a=time_a,
                time_b=time_b,
                data_jogo=data_jogo,
                horario_jogo=horario_jogo or None,
                local=local or '',
                finalizado=bool(data.get('finalizado', False))
            )
            return JsonResponse({'success': True, 'jogo': jogo_to_dict(jogo)})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

@method_decorator(csrf_exempt, name='dispatch')
class APIJogoDetailView(View):
    def put(self, request, pk):
        if not request.user.is_authenticated or not request.user.is_comissao:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        jogo = get_object_or_404(Jogo, pk=pk)
        try:
            data = json.loads(request.body)
            
            if data.get('modalidade_id'):
                jogo.modalidade = get_object_or_404(Modalidade, pk=data.get('modalidade_id'))
            if data.get('time_a_id'):
                jogo.time_a = get_object_or_404(User, pk=data.get('time_a_id'), role='REPRESENTANTE')
            if data.get('time_b_id'):
                jogo.time_b = get_object_or_404(User, pk=data.get('time_b_id'), role='REPRESENTANTE')
                
            jogo.data_jogo = data.get('data_jogo', jogo.data_jogo)
            jogo.horario_jogo = data.get('horario_jogo', jogo.horario_jogo)
            jogo.local = data.get('local', jogo.local)
            jogo.finalizado = bool(data.get('finalizado', jogo.finalizado))
            
            jogo.save()
            return JsonResponse({'success': True, 'jogo': jogo_to_dict(jogo)})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
            
    def delete(self, request, pk):
        if not request.user.is_authenticated or not request.user.is_comissao:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        jogo = get_object_or_404(Jogo, pk=pk)
        jogo.delete()
        return JsonResponse({'success': True})


# --- DELEGAÇÕES ---

@method_decorator(csrf_exempt, name='dispatch')
class APIDelegacoesView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        # Comissão pode listar todas as delegações ativas para avaliação
        if request.user.is_comissao:
            representantes = User.objects.filter(role='REPRESENTANTE').order_by('nome_delegacao')
            delegacoes_data = []
            for r in representantes:
                inscricao = getattr(r, 'inscricao', None)
                insc_data = None
                if inscricao:
                    insc_data = {
                        'id': inscricao.id,
                        'status': inscricao.status,
                        'justificativa': inscricao.justificativa,
                        'data_envio': inscricao.data_envio.isoformat(),
                        'modalidades': [
                            {
                                'id': im.id,
                                'modalidade_nome': im.modalidade.nome,
                                'modalidade_genero': im.modalidade.get_genero_display(),
                                'atletas': [atleta_to_dict(at) for at in im.atletas.all()]
                            }
                            for im in inscricao.modalidades.all()
                        ]
                    }
                
                # Lista atletas delegação
                atletas_list = [atleta_to_dict(at) for at in r.atletas.all()]
                
                delegacoes_data.append({
                    'representante': user_to_dict(r),
                    'inscricao': insc_data,
                    'atletas': atletas_list
                })
            return JsonResponse({'delegacoes': delegacoes_data})
        else:
            # Representante pode listar apenas a sua delegacao
            # Pode ser útil para popular dropdowns
            representantes = User.objects.filter(role='REPRESENTANTE', perfil_completo=True).order_by('nome_delegacao')
            return JsonResponse({'delegacoes': [{'id': r.id, 'nome_delegacao': r.nome_delegacao or r.email} for r in representantes]})

@method_decorator(csrf_exempt, name='dispatch')
class APIDelegacaoAvaliarView(View):
    def post(self, request, pk):
        if not request.user.is_authenticated or not request.user.is_comissao:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        representante = get_object_or_404(User, pk=pk, role='REPRESENTANTE')
        inscricao = get_object_or_404(Inscricao, delegacao=representante)
        
        try:
            data = json.loads(request.body)
            status = data.get('status')
            justificativa = data.get('justificativa', '')
            
            if status in ['deferido', 'indeferido', 'pendente']:
                if status != 'indeferido':
                    justificativa = ''
                
                inscricao.status = status
                inscricao.justificativa = justificativa
                inscricao.save()
                
                representante.status_delegacao = status
                representante.justificativa_delegacao = justificativa
                representante.save()
                
                # Notifica os representantes e membros da delegação
                if status == 'deferido':
                    msg_notif = "Sua inscrição foi avaliada e DEFERIDA (aprovada) pela comissão organizadora."
                elif status == 'indeferido':
                    msg_notif = f"Sua inscrição foi avaliada e INDEFERIDA (recusada) pela comissão organizadora. Motivo: {justificativa}"
                else:
                    msg_notif = "Sua inscrição foi alterada para PENDENTE de análise."
                    
                usuarios_delegacao = User.objects.filter(Q(id=representante.id) | Q(parent_delegate=representante))
                for usr in usuarios_delegacao:
                    Notificacao.objects.create(
                        usuario=usr,
                        mensagem=msg_notif,
                        link='/inscricao/detalhe/'
                    )
                
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'error': 'Status inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


# --- PRÉ-SÚMULAS ---

@method_decorator(csrf_exempt, name='dispatch')
class APIPreSumulasView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        user = request.user
        delegacao = user.delegacao_ativa
        
        # Filtra os jogos
        if user.is_comissao:
            jogos = Jogo.objects.all().order_by('-data_jogo', '-horario_jogo')
        else:
            if delegacao.status_delegacao != 'deferido':
                return JsonResponse({'jogos': [], 'error': 'Delegação não está deferida'}, status=403)
            jogos = Jogo.objects.filter(Q(time_a=delegacao) | Q(time_b=delegacao)).order_by('-data_jogo', '-horario_jogo')
            
        # Para cada jogo, busca as pré-súmulas
        jogos_data = []
        for jogo in jogos:
            presumulas_data = []
            
            # Se for admin, vê todas. Se for representante, só vê a dele.
            if user.is_comissao:
                presumulas = PreSumula.objects.filter(jogo=jogo)
            else:
                presumulas = PreSumula.objects.filter(jogo=jogo, representante=delegacao)
                
            for ps in presumulas:
                escalacao = []
                for pa in ps.escalacao.all().select_related('atleta'):
                    escalacao.append({
                        'atleta': atleta_to_dict(pa.atleta),
                        'numero_camisa': pa.numero_camisa
                    })
                    
                presumulas_data.append({
                    'id': ps.id,
                    'representante_id': ps.representante_id,
                    'representante_nome': ps.representante.nome_delegacao or ps.representante.email,
                    'tecnico': ps.tecnico,
                    'escalacao': escalacao,
                    'data_criacao': ps.data_criacao.isoformat()
                })
                
            jogos_data.append({
                'jogo': jogo_to_dict(jogo),
                'presumulas': presumulas_data
            })
            
        return JsonResponse({'jogos': jogos_data})
        
    def post(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        user = request.user
        delegacao = user.delegacao_ativa
        if not user.is_comissao and delegacao.status_delegacao != 'deferido':
            return JsonResponse({'error': 'Acesso Bloqueado: Sua delegação não está deferida.'}, status=403)
            
        try:
            data = json.loads(request.body)
            jogo_id = data.get('jogo_id')
            atletas_escalados = data.get('atletas', []) # lista de objetos { atleta_id: ..., camisa: ... }
            tecnico = data.get('tecnico', '').strip()
            
            jogo = get_object_or_404(Jogo, pk=jogo_id)
            if not user.is_comissao and jogo.time_a != delegacao and jogo.time_b != delegacao:
                return JsonResponse({'error': 'Você não tem permissão para preencher a pré-súmula para este jogo.'}, status=403)

            # Verifica limite de 1h antes do jogo
            if not user.is_comissao and jogo.is_presumula_deadline_passed:
                return JsonResponse({'error': 'Prazo encerrado: A pré-súmula deve ser preenchida em até 1h antes do jogo. WO foi aplicado.'}, status=400)
                
            if PreSumula.objects.filter(jogo=jogo, representante=delegacao).exists():
                return JsonResponse({'error': 'Você já enviou uma pré-súmula para este jogo.'}, status=400)
                
            presumula = PreSumula.objects.create(
                jogo=jogo,
                representante=delegacao,
                tecnico=tecnico
            )
            
            for item in atletas_escalados:
                atleta_id = item.get('atleta_id')
                numero_camisa = item.get('camisa')
                if atleta_id and numero_camisa is not None:
                    PreSumulaAtleta.objects.create(
                        presumula=presumula,
                        atleta_id=atleta_id,
                        numero_camisa=int(numero_camisa)
                    )
                    
            return JsonResponse({'success': True, 'id': presumula.id})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

@method_decorator(csrf_exempt, name='dispatch')
class APIPreSumulaDetailView(View):
    def get(self, request, pk):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        presumula = get_object_or_404(PreSumula, pk=pk)
        if not request.user.is_comissao and presumula.representante != request.user.delegacao_ativa:
            return JsonResponse({'error': 'Não autorizado'}, status=403)
            
        escalacao = []
        for pa in presumula.escalacao.all().select_related('atleta'):
            escalacao.append({
                'atleta': atleta_to_dict(pa.atleta),
                'numero_camisa': pa.numero_camisa
            })
            
        return JsonResponse({
            'id': presumula.id,
            'jogo': jogo_to_dict(presumula.jogo),
            'representante': user_to_dict(presumula.representante),
            'tecnico': presumula.tecnico,
            'escalacao': escalacao,
            'data_criacao': presumula.data_criacao.isoformat()
        })
        
    def put(self, request, pk):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        presumula = get_object_or_404(PreSumula, pk=pk)
        if not request.user.is_comissao and presumula.representante != request.user.delegacao_ativa:
            return JsonResponse({'error': 'Não autorizado'}, status=403)

        # Verifica limite de 1h antes do jogo
        if not request.user.is_comissao and presumula.jogo.is_presumula_deadline_passed:
            return JsonResponse({'error': 'Prazo encerrado: A pré-súmula não pode mais ser editada (limite de 1h antes do jogo).'}, status=400)
            
        try:
            data = json.loads(request.body)
            atletas_escalados = data.get('atletas', []) # lista de objetos { atleta_id: ..., camisa: ... }
            tecnico = data.get('tecnico', '')
            
            # Limpa escalações antigas
            PreSumulaAtleta.objects.filter(presumula=presumula).delete()
            
            for item in atletas_escalados:
                atleta_id = item.get('atleta_id')
                numero_camisa = item.get('camisa')
                if atleta_id and numero_camisa is not None:
                    PreSumulaAtleta.objects.create(
                        presumula=presumula,
                        atleta_id=atleta_id,
                        numero_camisa=int(numero_camisa)
                    )
            
            if tecnico is not None:
                presumula.tecnico = tecnico.strip()
                presumula.save()
                
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


# --- INSCRIÇÃO FLUXO ---

@method_decorator(csrf_exempt, name='dispatch')
class APIInscricaoFluxoView(View):
    """
    Substitui a lógica de sessões e passos por um endpoint robusto de inscrição direta.
    """
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        user = request.user
        if user.is_comissao:
            return JsonResponse({'error': 'Comissão não se inscreve'}, status=403)
            
        delegacao = user.delegacao_ativa
        inscricao = getattr(delegacao, 'inscricao', None)
        if not inscricao:
            return JsonResponse({'inscricao': None})
            
        # Detalhes da inscrição
        modalidades_inscritas = []
        for im in inscricao.modalidades.all():
            modalidades_inscritas.append({
                'id': im.id,
                'modalidade': modalidade_to_dict(im.modalidade),
                'atletas': [atleta_to_dict(at) for at in im.atletas.all()]
            })
            
        return JsonResponse({
            'inscricao': {
                'id': inscricao.id,
                'status': inscricao.status,
                'status_display': inscricao.get_status_display(),
                'justificativa': inscricao.justificativa,
                'data_envio': inscricao.data_envio.isoformat(),
                'modalidades': modalidades_inscritas,
                'atletas_inscritos_count': len(inscricao.atletas_inscritos)
            }
        })
        
    def post(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        user = request.user
        delegacao = user.delegacao_ativa
        if user.is_comissao:
            return JsonResponse({'error': 'Comissão não se inscreve'}, status=403)
            
        inscricao = getattr(delegacao, 'inscricao', None)
        if inscricao and inscricao.status != 'indeferido':
            return JsonResponse({'error': 'Você já possui uma inscrição activa.'}, status=400)
            
        try:
            data = json.loads(request.body)
            # Espera { modalidades_ids: [...], atletas_ids: [...] }
            modalidades_ids = data.get('modalidades_ids', [])
            atletas_ids = data.get('atletas_ids', [])
            
            if not modalidades_ids:
                return JsonResponse({'error': 'Selecione ao menos uma modalidade.'}, status=400)
            if not atletas_ids:
                return JsonResponse({'error': 'Selecione ao menos um atleta.'}, status=400)
                
            # Verifica e cria a inscrição
            if inscricao:
                # Se for indeferida, deleta anterior
                inscricao.delete()
                
            inscricao = Inscricao.objects.create(
                delegacao=delegacao,
                status='pendente'
            )
            
            selected_modalidades = Modalidade.objects.filter(id__in=modalidades_ids)
            selected_atletas = Atleta.objects.filter(id__in=atletas_ids, cadastrado_por=delegacao)
            
            for mod in selected_modalidades:
                insc_mod = InscricaoModalidade.objects.create(inscricao=inscricao, modalidade=mod)
                insc_mod.atletas.set(selected_atletas)
                
            delegacao.status_delegacao = 'pendente'
            delegacao.justificativa_delegacao = ''
            delegacao.save()
            
            # Notifica a comissão organizadora de que há uma nova inscrição
            comissao = User.objects.filter(role='COMISSAO')
            for admin in comissao:
                Notificacao.objects.create(
                    usuario=admin,
                    mensagem=f"Nova inscrição pendente de avaliação da delegação {delegacao.nome_delegacao or delegacao.email}.",
                    link='/comissao/delegacoes/'
                )
            
            return JsonResponse({'success': True, 'inscricao_id': inscricao.id})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

@method_decorator(csrf_exempt, name='dispatch')
class APIInscricaoRefazerView(View):
    def post(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        user = request.user
        delegacao = user.delegacao_ativa
        inscricao = getattr(delegacao, 'inscricao', None)
        if not inscricao:
            return JsonResponse({'error': 'Nenhuma inscrição encontrada'}, status=404)
            
        if inscricao.status == 'indeferido':
            inscricao.delete()
            delegacao.status_delegacao = 'pendente'
            delegacao.save()
            return JsonResponse({'success': True, 'message': 'Inscrição cancelada. Pronta para refazer.'})
        elif inscricao.status == 'pendente':
            return JsonResponse({'error': 'Sua inscrição está pendente e não pode ser cancelada.'}, status=400)
        else:
            return JsonResponse({'error': 'Sua inscrição já foi deferida e não pode ser modificada.'}, status=400)


# --- COMISSÃO WHITELIST ---

@method_decorator(csrf_exempt, name='dispatch')
class APIWhitelistView(View):
    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_comissao:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        whitelist = ComissaoWhitelist.objects.all().order_by('-data_adicao')
        whitelist_data = [{'id': w.id, 'email': w.email, 'data_adicao': w.data_adicao.isoformat()} for w in whitelist]
        return JsonResponse({'whitelist': whitelist_data})
        
    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_comissao:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        try:
            data = json.loads(request.body)
            email = data.get('email', '').strip().lower()
            if not email:
                return JsonResponse({'error': 'O e-mail é obrigatório.'}, status=400)
                
            if ComissaoWhitelist.objects.filter(email__iexact=email).exists():
                return JsonResponse({'error': 'O e-mail já está na whitelist.'}, status=400)
                
            item = ComissaoWhitelist.objects.create(email=email)
            return JsonResponse({'success': True, 'id': item.id, 'email': item.email, 'data_adicao': item.data_adicao.isoformat()})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

@method_decorator(csrf_exempt, name='dispatch')
class APIWhitelistDetailView(View):
    def delete(self, request, pk):
        if not request.user.is_authenticated or not request.user.is_comissao:
            return JsonResponse({'error': 'Não autorizado'}, status=401)
            
        item = get_object_or_404(ComissaoWhitelist, pk=pk)
        item.delete()
        return JsonResponse({'success': True})
