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


class AtletaStatusTestCase(TestCase):
    def setUp(self):
        self.delegacao = User.objects.create_user(
            email='delegado@example.com',
            nome_completo='Delegado Teste',
            role='REPRESENTANTE',
            cpf='366.146.971-10',
            nome_delegacao='Delegação Teste'
        )
        self.staff_user = User.objects.create_superuser(
            email='admin@example.com',
            nome_completo='Admin Comissão',
            role='COMISSAO',
            is_staff=True
        )
        self.atleta = Atleta.objects.create(
            nome_completo='Atleta Teste',
            email='atleta@example.com',
            matricula='123456',
            curso='Sistemas de Informação',
            genero='M',
            cadastrado_por=self.delegacao
        )

    def test_default_status_is_nao_avaliado(self):
        self.assertEqual(self.atleta.status_avaliacao, 'nao_avaliado')
        self.assertFalse(self.atleta.em_conformidade)

    def test_eval_atleta_deferido(self):
        from django.urls import reverse
        self.client.force_login(self.staff_user)
        url = reverse('avaliar_atleta', kwargs={'pk': self.atleta.id})
        response = self.client.post(url, data={
            'status': 'deferido',
            'justificativa': ''
        })
        self.assertEqual(response.status_code, 302)
        
        self.atleta.refresh_from_db()
        self.assertEqual(self.atleta.status_avaliacao, 'deferido')
        self.assertTrue(self.atleta.em_conformidade)

    def test_eval_atleta_indeferido(self):
        from django.urls import reverse
        self.client.force_login(self.staff_user)
        url = reverse('avaliar_atleta', kwargs={'pk': self.atleta.id})
        response = self.client.post(url, data={
            'status': 'indeferido',
            'justificativa': 'Documento ilegível',
            'permite_correcao': 'on'
        })
        self.assertEqual(response.status_code, 302)
        
        self.atleta.refresh_from_db()
        self.assertEqual(self.atleta.status_avaliacao, 'indeferido')
        self.assertFalse(self.atleta.em_conformidade)
        self.assertEqual(self.atleta.justificativa_inconformidade, 'Documento ilegível')
        self.assertTrue(self.atleta.permite_correcao)

    def test_reset_conformidade(self):
        from django.urls import reverse
        self.atleta.status_avaliacao = 'indeferido'
        self.atleta.em_conformidade = False
        self.atleta.save()
        
        self.client.force_login(self.staff_user)
        url = reverse('atleta_reset_conformidade', kwargs={'pk': self.atleta.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        
        self.atleta.refresh_from_db()
        self.assertEqual(self.atleta.status_avaliacao, 'deferido')
        self.assertTrue(self.atleta.em_conformidade)


class InscricaoNotificacoesTestCase(TestCase):
    def setUp(self):
        # 1. Commission / Admin user
        self.staff_user = User.objects.create_superuser(
            email='admin@example.com',
            nome_completo='Admin Comissão',
            role='COMISSAO',
            is_staff=True
        )
        # 2. Main delegate
        self.delegacao = User.objects.create_user(
            email='delegado@example.com',
            nome_completo='Delegado Teste',
            role='REPRESENTANTE',
            cpf='366.146.971-10',
            nome_delegacao='Delegação Teste',
            link_comprovante_pagamento='https://example.com/payment.pdf'
        )
        # 3. Sub delegate / Member
        self.sub_delegate = User.objects.create_user(
            email='membro@example.com',
            nome_completo='Membro Auxiliar',
            role='REPRESENTANTE',
            parent_delegate=self.delegacao
        )
        # 4. Modality and Athlete
        self.modalidade = Modalidade.objects.create(
            nome='Futsal',
            genero='M'
        )
        self.atleta = Atleta.objects.create(
            nome_completo='Atleta Teste',
            email='atleta@example.com',
            matricula='123456',
            curso='Sistemas de Informação',
            genero='M',
            cadastrado_por=self.delegacao
        )

    def test_inscription_submission_notifies_commission(self):
        from django.urls import reverse
        from core.models import Notificacao
        
        # Force session data for selected modalities
        session = self.client.session
        session['inscricao_modalidades_ids'] = [self.modalidade.id]
        session.save()

        self.client.force_login(self.delegacao)
        url = reverse('inscricao_passo2')
        response = self.client.post(url, data={
            'atletas': [self.atleta.id]
        })
        self.assertEqual(response.status_code, 302)

        # Check notifications for commission
        notifs = Notificacao.objects.filter(usuario=self.staff_user)
        self.assertEqual(notifs.count(), 1)
        self.assertIn("Nova inscrição pendente de avaliação", notifs.first().mensagem)
        self.assertEqual(notifs.first().link, '/comissao/delegacoes/')

    def test_inscription_succeeds_without_comprovante(self):
        from django.urls import reverse
        # Clear the payment receipt
        self.delegacao.link_comprovante_pagamento = ''
        self.delegacao.save()

        # Force session data for selected modalities
        session = self.client.session
        session['inscricao_modalidades_ids'] = [self.modalidade.id]
        session.save()

        self.client.force_login(self.delegacao)
        url = reverse('inscricao_passo2')
        response = self.client.post(url, data={
            'atletas': [self.atleta.id]
        })
        # Should succeed and redirect to details page (status 302)
        self.assertEqual(response.status_code, 302)

    def test_inscription_evaluation_notifies_delegation(self):
        from django.urls import reverse
        from core.models import Inscricao, Notificacao

        # Create inscription
        inscricao = Inscricao.objects.create(
            delegacao=self.delegacao,
            status='pendente'
        )

        self.client.force_login(self.staff_user)
        url = reverse('avaliar_delegacao', kwargs={'pk': self.delegacao.id})
        
        # Test deferido notification
        response = self.client.post(url, data={
            'status': 'deferido',
            'justificativa': ''
        })
        self.assertEqual(response.status_code, 302)

        # Main delegate and sub delegate should both be notified
        notif_main = Notificacao.objects.filter(usuario=self.delegacao)
        notif_sub = Notificacao.objects.filter(usuario=self.sub_delegate)
        self.assertEqual(notif_main.count(), 1)
        self.assertEqual(notif_sub.count(), 1)
        self.assertIn("DEFERIDA", notif_main.first().mensagem)
        self.assertEqual(notif_main.first().link, '/inscricao/detalhe/')

        # Test indeferido notification
        response = self.client.post(url, data={
            'status': 'indeferido',
            'justificativa': 'Assinatura inválida'
        })
        self.assertEqual(response.status_code, 302)

        notif_main = Notificacao.objects.filter(usuario=self.delegacao).order_by('-id')
        self.assertIn("INDEFERIDA", notif_main.first().mensagem)
        self.assertIn("Assinatura inválida", notif_main.first().mensagem)

    def test_inscription_evaluation_clears_justification_when_deferido(self):
        from django.urls import reverse
        from core.models import Inscricao

        inscricao = Inscricao.objects.create(
            delegacao=self.delegacao,
            status='pendente'
        )

        self.client.force_login(self.staff_user)
        url = reverse('avaliar_delegacao', kwargs={'pk': self.delegacao.id})
        
        # 1. Reject first
        response = self.client.post(url, data={
            'status': 'indeferido',
            'justificativa': 'Assinatura inválida'
        })
        self.assertEqual(response.status_code, 302)
        
        inscricao.refresh_from_db()
        self.delegacao.refresh_from_db()
        self.assertEqual(inscricao.status, 'indeferido')
        self.assertEqual(inscricao.justificativa, 'Assinatura inválida')
        self.assertEqual(self.delegacao.status_delegacao, 'indeferido')
        self.assertEqual(self.delegacao.justificativa_delegacao, 'Assinatura inválida')

        # 2. Defer (Approve)
        response = self.client.post(url, data={
            'status': 'deferido',
            'justificativa': 'Assinatura inválida' # Pass old value as might happen in DOM
        })
        self.assertEqual(response.status_code, 302)
        
        inscricao.refresh_from_db()
        self.delegacao.refresh_from_db()
        self.assertEqual(inscricao.status, 'deferido')
        self.assertEqual(inscricao.justificativa, '')
        self.assertEqual(self.delegacao.status_delegacao, 'deferido')
        self.assertEqual(self.delegacao.justificativa_delegacao, '')


class PaymentReceiptTestCase(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_superuser(
            email='admin@example.com',
            nome_completo='Admin Comissão',
            role='COMISSAO',
            is_staff=True
        )
        self.delegacao = User.objects.create_user(
            email='delegado@example.com',
            nome_completo='Delegado Teste',
            role='REPRESENTANTE',
            cpf='366.146.971-10',
            nome_delegacao='Delegação Teste'
        )

    def test_upload_payment_receipt(self):
        from django.urls import reverse
        self.client.force_login(self.delegacao)
        url = reverse('enviar_comprovante_pagamento')
        response = self.client.post(url, data={
            'link_comprovante_pagamento': 'https://drive.google.com/file/d/receipt'
        })
        self.assertEqual(response.status_code, 302)
        
        # Verify stored data
        self.delegacao.refresh_from_db()
        self.assertEqual(self.delegacao.link_comprovante_pagamento, 'https://drive.google.com/file/d/receipt')
        self.assertEqual(self.delegacao.status_pagamento, 'nao_avaliado')

    def test_evaluate_payment_receipt(self):
        from django.urls import reverse
        # Assign receipt link first
        self.delegacao.link_comprovante_pagamento = 'https://drive.google.com/file/d/receipt'
        self.delegacao.save()

        self.client.force_login(self.staff_user)
        url = reverse('avaliar_pagamento', kwargs={'pk': self.delegacao.id})
        
        # Defer receipt
        response = self.client.post(url, data={
            'status': 'deferido',
            'justificativa': ''
        })
        self.assertEqual(response.status_code, 302)
        self.delegacao.refresh_from_db()
        self.assertEqual(self.delegacao.status_pagamento, 'deferido')

        # Indefer receipt
        response = self.client.post(url, data={
            'status': 'indeferido',
            'justificativa': 'Recibo ilegível'
        })
        self.assertEqual(response.status_code, 302)
        self.delegacao.refresh_from_db()
        self.assertEqual(self.delegacao.status_pagamento, 'indeferido')
        self.assertEqual(self.delegacao.justificativa_pagamento, 'Recibo ilegível')

    def test_upload_payment_receipt_resets_status(self):
        from django.urls import reverse
        # Set evaluated to indeferido
        self.delegacao.link_comprovante_pagamento = 'https://drive.google.com/file/d/receipt1'
        self.delegacao.status_pagamento = 'indeferido'
        self.delegacao.justificativa_pagamento = 'Recibo antigo'
        self.delegacao.save()

        # Upload new receipt
        self.client.force_login(self.delegacao)
        url = reverse('enviar_comprovante_pagamento')
        response = self.client.post(url, data={
            'link_comprovante_pagamento': 'https://drive.google.com/file/d/receipt2'
        })
        self.assertEqual(response.status_code, 302)
        
        # Verify reset status
        self.delegacao.refresh_from_db()
        self.assertEqual(self.delegacao.link_comprovante_pagamento, 'https://drive.google.com/file/d/receipt2')
        self.assertEqual(self.delegacao.status_pagamento, 'nao_avaliado')
        self.assertEqual(self.delegacao.justificativa_pagamento, '')

    def test_views_path_rendering(self):
        from django.urls import reverse
        from core.models import Inscricao

        # Create inscription so details page doesn't redirect
        Inscricao.objects.create(
            delegacao=self.delegacao,
            status='pendente'
        )

        self.client.force_login(self.delegacao)

        # 1. Test Athlete List View (Meus Atletas)
        response = self.client.get(reverse('atleta_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Meus Atletas")
        self.assertContains(response, "Comprovante de Pagamento Geral da Delegação")

        # 2. Test Bulk Create View (Cadastro de Atletas)
        response = self.client.get(reverse('atleta_bulk_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cadastro de Atletas")
        # Ensure the payment button was indeed moved (removed from here)
        self.assertNotContains(response, "Comprovante de Pagamento Geral da Delegação")

        # 3. Test Inscription Detail View (Status da Inscrição)
        response = self.client.get(reverse('inscricao_detail'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Comprovante de Pagamento Geral da Delegação")
        self.assertContains(response, "Modalidades de Interesse Selecionadas")
        self.assertContains(response, "Ver modalidades e atletas inscritos")


from django.core.management import call_command
from django.core.management.base import CommandError
from io import StringIO

class ResetInscricaoCommandTestCase(TestCase):
    def setUp(self):
        self.delegate = User.objects.create_user(
            email='delegate@example.com',
            nome_completo='Delegate Test',
            role='REPRESENTANTE',
            cpf='111.444.777-35',
            nome_delegacao='Delegação Teste'
        )
        # Create an inscription for the delegate
        from core.models import Inscricao
        self.inscricao = Inscricao.objects.create(
            delegacao=self.delegate,
            status='pendente'
        )
        self.delegate.status_delegacao = 'deferido'
        self.delegate.save()

    def test_reset_inscricao_success(self):
        from core.models import Inscricao
        out = StringIO()
        # Call the command to reset the inscription
        call_command('reset_inscricao', 'delegate@example.com', stdout=out)
        
        # Verify inscription is deleted
        self.assertFalse(Inscricao.objects.filter(delegacao=self.delegate).exists())
        
        # Verify status of delegation is reset to pendente
        self.delegate.refresh_from_db()
        self.assertEqual(self.delegate.status_delegacao, 'pendente')
        
        output = out.getvalue()
        self.assertIn('removida com sucesso', output)
        self.assertIn('resetado para "Pendente de Análise"', output)

    def test_reset_inscricao_no_inscricao(self):
        from core.models import Inscricao
        # Delete inscription first
        self.inscricao.delete()
        
        out = StringIO()
        call_command('reset_inscricao', 'delegate@example.com', stdout=out)
        
        # Verify status of delegation is still pendente
        self.delegate.refresh_from_db()
        self.assertEqual(self.delegate.status_delegacao, 'pendente')
        
        output = out.getvalue()
        self.assertIn('não possui nenhuma inscrição enviada', output)
        self.assertIn('resetado para "Pendente de Análise"', output)

    def test_reset_inscricao_non_existent_user(self):
        with self.assertRaises(CommandError) as context:
            call_command('reset_inscricao', 'nonexistent@example.com')
        self.assertIn('não foi encontrado', str(context.exception))

    def test_reset_inscricao_non_representative(self):
        # Create a non-representative user
        non_rep = User.objects.create_user(
            email='nonrep@example.com',
            nome_completo='Non Rep',
            role='COMISSAO'
        )
        with self.assertRaises(CommandError) as context:
            call_command('reset_inscricao', 'nonrep@example.com')
        self.assertIn('não é um Representante de Delegação', str(context.exception))


class AdminActionsTestCase(TestCase):
    def setUp(self):
        self.delegate = User.objects.create_user(
            email='delegate_admin@example.com',
            nome_completo='Delegate Admin Test',
            role='REPRESENTANTE',
            cpf='111.444.777-35',
            nome_delegacao='Delegação Admin Teste'
        )
        from core.models import Inscricao
        self.inscricao = Inscricao.objects.create(
            delegacao=self.delegate,
            status='pendente'
        )
        self.delegate.status_delegacao = 'deferido'
        self.delegate.save()

    def test_inscricao_admin_action(self):
        from core.admin import InscricaoAdmin
        from core.models import Inscricao
        from django.contrib.admin.sites import AdminSite
        
        site = AdminSite()
        admin_instance = InscricaoAdmin(Inscricao, site)
        
        queryset = Inscricao.objects.filter(delegacao=self.delegate)
        
        class MockRequest:
            pass
        request = MockRequest()
        admin_instance.message_user = lambda req, msg: None
        
        admin_instance.deletar_e_resetar_delegacao(request, queryset)
        
        self.assertFalse(Inscricao.objects.filter(delegacao=self.delegate).exists())
        self.delegate.refresh_from_db()
        self.assertEqual(self.delegate.status_delegacao, 'pendente')

    def test_user_admin_action(self):
        from users.admin import UserAdmin
        from django.contrib.admin.sites import AdminSite
        
        site = AdminSite()
        admin_instance = UserAdmin(User, site)
        
        queryset = User.objects.filter(id=self.delegate.id)
        
        class MockRequest:
            pass
        request = MockRequest()
        admin_instance.message_user = lambda req, msg: None
        
        admin_instance.resetar_inscricao_delegados(request, queryset)
        
        from core.models import Inscricao
        self.assertFalse(Inscricao.objects.filter(delegacao=self.delegate).exists())
        self.delegate.refresh_from_db()
        self.assertEqual(self.delegate.status_delegacao, 'pendente')

    def test_inscricao_modalidade_inline(self):
        from core.admin import InscricaoAdmin, InscricaoModalidadeInline
        from core.models import Inscricao, Atleta, InscricaoModalidade
        from django.contrib.admin.sites import AdminSite
        
        site = AdminSite()
        admin_instance = InscricaoAdmin(Inscricao, site)
        
        # Verify inline is present
        self.assertIn(InscricaoModalidadeInline, admin_instance.inlines)
        
        # Create other delegate and athletes to test filtering
        other_delegate = User.objects.create_user(
            email='other_delegate@example.com',
            nome_completo='Other Delegate',
            role='REPRESENTANTE',
            cpf='366.146.971-10'
        )
        
        # Athlete belonging to self.delegate
        atleta_ok = Atleta.objects.create(
            nome_completo="Atleta OK",
            email="atleta_ok@example.com",
            matricula="123",
            curso="Educação Física",
            cadastrado_por=self.delegate
        )
        
        # Athlete belonging to other_delegate
        atleta_other = Atleta.objects.create(
            nome_completo="Atleta Other",
            email="atleta_other@example.com",
            matricula="456",
            curso="Educação Física",
            cadastrado_por=other_delegate
        )
        
        # Test inline formfield filtering
        inline_instance = InscricaoModalidadeInline(Inscricao, site)
        
        class MockResolverMatch:
            kwargs = {'object_id': self.inscricao.pk}
            
        class MockRequest:
            resolver_match = MockResolverMatch()
            
        db_field = InscricaoModalidade._meta.get_field('atletas')
        formfield = inline_instance.formfield_for_manytomany(db_field, request=MockRequest())
        
        queryset = formfield.queryset
        self.assertIn(atleta_ok, queryset)
        self.assertNotIn(atleta_other, queryset)

    def test_resumo_inscricoes_view(self):
        from django.urls import reverse
        from core.models import Campus, Atleta
        
        # Create a Campus
        campus = Campus.objects.create(nome="Campus Teste")
        
        # Create an athlete
        Atleta.objects.create(
            nome_completo="Atleta Teste",
            email="atleta@example.com",
            matricula="789",
            curso="Educação Física",
            campus=campus,
            cadastrado_por=self.delegate
        )
        
        # 1. Test representing user (has no staff access)
        self.client.force_login(self.delegate)
        response = self.client.get(reverse('resumo_inscricoes'))
        # user_passes_test redirects to login page by default
        self.assertEqual(response.status_code, 302)
        
        # 2. Create and login as COMISSAO user
        comissao_user = User.objects.create_user(
            email='comissao_test@example.com',
            nome_completo='Comissao Test',
            role='COMISSAO',
            cpf='181.498.521-23'
        )
        # Verify automatic is_staff=True on save
        self.assertTrue(comissao_user.is_staff)
        
        self.client.force_login(comissao_user)
        response = self.client.get(reverse('resumo_inscricoes'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/resumo_inscricoes.html')
        
        # Check context variables
        self.assertEqual(response.context['total_delegacoes'], 1)
        self.assertEqual(response.context['total_atletas'], 1)
        self.assertIn('campi', response.context)
        self.assertIn('chart_campus_labels_json', response.context)
        self.assertIn('chart_datasets_modalidades_json', response.context)








