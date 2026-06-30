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

