from django.test import TestCase
from django.contrib.auth import get_user_model
from users.models import MembroDelegacao
from core.models import Atleta

User = get_user_model()

class DelegationSharingTestCase(TestCase):
    def setUp(self):
        # Cria o delegado principal
        self.delegate = User.objects.create_user(
            email='principal@example.com',
            nome_completo='Delegado Principal',
            role='REPRESENTANTE',
            cpf='111.444.777-35',
            nome_delegacao='Delegação UFVJM'
        )
        
        # O perfil do principal deve estar completo
        self.assertTrue(self.delegate.perfil_completo)

    def test_delegacao_ativa_property(self):
        # Delegado principal deve ter ele mesmo como delegacao_ativa
        self.assertEqual(self.delegate.delegacao_ativa, self.delegate)
        
        # Cria um sub-delegado/membro
        sub_delegate = User.objects.create_user(
            email='membro@example.com',
            nome_completo='Membro Auxiliar',
            role='REPRESENTANTE',
            parent_delegate=self.delegate
        )
        
        # Sub-delegado deve ter o delegado principal como delegacao_ativa
        self.assertEqual(sub_delegate.delegacao_ativa, self.delegate)
        # Perfil completo do sub-delegado deve ser copiado do pai
        self.assertTrue(sub_delegate.perfil_completo)

    def test_auto_linking_existing_user(self):
        # Cria um usuário sem vínculo
        membro_user = User.objects.create_user(
            email='membro@example.com',
            nome_completo='Membro Auxiliar',
            role='REPRESENTANTE'
        )
        self.assertFalse(membro_user.perfil_completo)
        self.assertNil = lambda x: self.assertIsNone(x)
        self.assertIsNone(membro_user.parent_delegate)
        
        # Adiciona na lista de membros autorizados
        membro_auth = MembroDelegacao.objects.create(
            delegado_principal=self.delegate,
            email='membro@example.com'
        )
        
        # O usuário existente deve ser vinculado e ter perfil_completo copiado automaticamente
        membro_user.refresh_from_db()
        self.assertEqual(membro_user.parent_delegate, self.delegate)
        self.assertTrue(membro_user.perfil_completo)

    def test_unlinking_on_member_removal(self):
        # Cria o vinculo adicionando o membro
        membro_auth = MembroDelegacao.objects.create(
            delegado_principal=self.delegate,
            email='membro@example.com'
        )
        
        # Cria o usuário correspondente
        membro_user = User.objects.create_user(
            email='membro@example.com',
            nome_completo='Membro Auxiliar',
            role='REPRESENTANTE',
            parent_delegate=self.delegate
        )
        
        self.assertEqual(membro_user.parent_delegate, self.delegate)
        
        # Remove a autorização
        membro_auth.delete()
        
        # O usuário correspondente deve ser desvinculado
        membro_user.refresh_from_db()
        self.assertIsNone(membro_user.parent_delegate)
        self.assertFalse(membro_user.perfil_completo)

    def test_profile_completion_sync(self):
        # Cria o sub-delegado
        sub_delegate = User.objects.create_user(
            email='membro@example.com',
            nome_completo='Membro Auxiliar',
            role='REPRESENTANTE',
            parent_delegate=self.delegate
        )
        self.assertTrue(sub_delegate.perfil_completo)
        
        # Incompleta o perfil do pai (remove o CPF, por exemplo)
        self.delegate.cpf = None
        self.delegate.save()
        
        # O perfil do pai e do sub-delegado devem ficar incompletos
        self.assertFalse(self.delegate.perfil_completo)
        
        sub_delegate.refresh_from_db()
        self.assertFalse(sub_delegate.perfil_completo)


from datetime import timedelta
from django.utils import timezone
from core.forms import JogoForm
from core.models import Modalidade, Jogo

class JogoFormValidationTestCase(TestCase):
    def setUp(self):
        # Cria duas delegações homologadas
        self.time_a = User.objects.create_user(
            email='timea@example.com',
            nome_completo='Time A',
            role='REPRESENTANTE',
            status_delegacao='deferido'
        )
        self.time_b = User.objects.create_user(
            email='timeb@example.com',
            nome_completo='Time B',
            role='REPRESENTANTE',
            status_delegacao='deferido'
        )
        # Cria uma modalidade
        self.modalidade = Modalidade.objects.create(
            nome='Futsal',
            genero='M'
        )
        # Cria um staff user
        self.staff_user = User.objects.create_user(
            email='staff@example.com',
            nome_completo='Staff User',
            role='COMISSAO',
            is_staff=True
        )

    def test_past_date_is_invalid(self):
        # Data de ontem
        ontem = timezone.localdate() - timedelta(days=1)
        form_data = {
            'modalidade': self.modalidade.id,
            'time_a': self.time_a.id,
            'time_b': self.time_b.id,
            'data_jogo': ontem,
            'horario_jogo': '15:00',
            'local': 'Quadra A',
            'finalizado': False
        }
        form = JogoForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('data_jogo', form.errors)
        self.assertEqual(form.errors['data_jogo'][0], "A data do jogo não pode ser no passado.")

    def test_future_date_is_valid(self):
        # Data de amanhã
        amanha = timezone.localdate() + timedelta(days=1)
        form_data = {
            'modalidade': self.modalidade.id,
            'time_a': self.time_a.id,
            'time_b': self.time_b.id,
            'data_jogo': amanha,
            'horario_jogo': '15:00',
            'local': 'Quadra A',
            'finalizado': False
        }
        form = JogoForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_past_time_today_is_invalid(self):
        hoje = timezone.localdate()
        # Horário 1 hora atrás
        uma_hora_atras = (timezone.localtime() - timedelta(hours=1)).time()
        form_data = {
            'modalidade': self.modalidade.id,
            'time_a': self.time_a.id,
            'time_b': self.time_b.id,
            'data_jogo': hoje,
            'horario_jogo': uma_hora_atras.strftime('%H:%M'),
            'local': 'Quadra A',
            'finalizado': False
        }
        form = JogoForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('horario_jogo', form.errors)
        self.assertEqual(form.errors['horario_jogo'][0], "O horário do jogo não pode ser no passado para o dia de hoje.")

    def test_create_game_past_date_via_view(self):
        from django.urls import reverse
        self.client.force_login(self.staff_user)
        ontem = timezone.localdate() - timedelta(days=1)
        form_data = {
            'modalidade': self.modalidade.id,
            'time_a': self.time_a.id,
            'time_b': self.time_b.id,
            'data_jogo': ontem.strftime('%Y-%m-%d'),
            'horario_jogo': '15:00',
            'local': 'Quadra A',
            'finalizado': False
        }
        response = self.client.post(reverse('jogo_create'), data=form_data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'data_jogo', "A data do jogo não pode ser no passado.")


class RecursosTestCase(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_superuser(
            email='admin@example.com',
            nome_completo='Admin Comissão',
            role='COMISSAO'
        )
        self.time_a = User.objects.create_user(
            email='timea@example.com',
            nome_completo='Delegado A',
            role='REPRESENTANTE',
            cpf='366.146.971-10',
            nome_delegacao='Atlética A'
        )
        self.time_b = User.objects.create_user(
            email='timeb@example.com',
            nome_completo='Delegado B',
            role='REPRESENTANTE',
            cpf='181.498.521-23',
            nome_delegacao='Atlética B'
        )
        self.time_c = User.objects.create_user(
            email='timec@example.com',
            nome_completo='Delegado C',
            role='REPRESENTANTE',
            cpf='069.258.583-45',
            nome_delegacao='Atlética C'
        )
        
        from core.models import Modalidade, Jogo
        self.modalidade = Modalidade.objects.create(
            nome='Futsal',
            genero='M',
            limite_minimo_jogadores=5,
            limite_maximo_jogadores=12,
            inscricoes_abertas=True
        )
        
        # Jogo finalizado
        self.jogo = Jogo.objects.create(
            modalidade=self.modalidade,
            data_jogo=timezone.localdate(),
            horario_jogo='15:00',
            time_a=self.time_a,
            time_b=self.time_b,
            local='Quadra A',
            finalizado=True,
            data_hora_fim=timezone.now() # finalizado agora
        )

    def test_recurso_creation_within_window(self):
        from django.urls import reverse
        self.client.force_login(self.time_a)
        
        url = reverse('recurso_create', kwargs={'jogo_id': self.jogo.id})
        # GET do form
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # POST do form
        post_data = {
            'titulo': 'Irregularidade',
            'corpo': 'Atleta escalado de forma irregular.',
            'link_anexo': 'https://drive.google.com/test'
        }
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302) # Redirects to detail page
        
        from core.models import Recurso, Notificacao
        recurso = Recurso.objects.get(jogo=self.jogo, requerente=self.time_a)
        self.assertEqual(recurso.titulo, 'Irregularidade')
        self.assertEqual(recurso.status, 'aberto')
        
        # Notificação criada para a comissão
        notif = Notificacao.objects.filter(usuario=self.staff_user)
        self.assertTrue(notif.exists())
        self.assertIn('Novo recurso interposto', notif.first().mensagem)

    def test_recurso_creation_expired_window(self):
        from django.urls import reverse
        # Altera fim do jogo para 2 horas atrás
        self.jogo.data_hora_fim = timezone.now() - timedelta(hours=2)
        self.jogo.save()
        
        self.client.force_login(self.time_a)
        url = reverse('recurso_create', kwargs={'jogo_id': self.jogo.id})
        response = self.client.post(url, data={
            'titulo': 'Irregularidade',
            'corpo': 'Atleta escalado de forma irregular.'
        })
        self.assertEqual(response.status_code, 302) # Redirect back with error
        
        from core.models import Recurso
        self.assertFalse(Recurso.objects.filter(jogo=self.jogo, requerente=self.time_a).exists())

    def test_recurso_creation_unrelated_team(self):
        from django.urls import reverse
        self.client.force_login(self.time_c)
        url = reverse('recurso_create', kwargs={'jogo_id': self.jogo.id})
        response = self.client.post(url, data={
            'titulo': 'Irregularidade',
            'corpo': 'Atleta escalado de forma irregular.'
        })
        self.assertEqual(response.status_code, 302)
        
        from core.models import Recurso
        self.assertFalse(Recurso.objects.filter(jogo=self.jogo, requerente=self.time_c).exists())

    def test_commission_reply_and_close(self):
        from django.urls import reverse
        from core.models import Recurso, RecursoMensagem, Notificacao
        recurso = Recurso.objects.create(
            jogo=self.jogo,
            requerente=self.time_a,
            titulo='Protesto',
            corpo='Conteúdo'
        )
        
        self.client.force_login(self.staff_user)
        url = reverse('recurso_mensagem_enviar', kwargs={'pk': recurso.id})
        
        # Envia parecer e encerra
        response = self.client.post(url, data={
            'texto': 'Parecer deferido.',
            'novo_status': 'encerrado'
        })
        self.assertEqual(response.status_code, 302)
        
        recurso.refresh_from_db()
        self.assertEqual(recurso.status, 'encerrado')
        
        # Mensagem gravada
        msg = RecursoMensagem.objects.filter(recurso=recurso, remetente=self.staff_user)
        self.assertTrue(msg.exists())
        self.assertEqual(msg.first().texto, 'Parecer deferido.')
        
        # Notificação criada para o requerente
        notif = Notificacao.objects.filter(usuario=self.time_a)
        self.assertTrue(notif.exists())
        self.assertIn('respondido e encerrado', notif.first().mensagem)

