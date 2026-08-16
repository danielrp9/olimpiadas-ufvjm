from datetime import date, time
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from agendamento.models import ConfiguracaoGeral, DataDisponivel, RecursoLocal, CenarioExecucao

User = get_user_model()


class AgendamentoViewsTests(TestCase):
    """
    Testes de rotas, views, permissões e formulários do módulo de agendamento.
    """

    def setUp(self):
        self.client = Client()
        self.comissao_user = User.objects.create_user(
            email="comissao@ufvjm.edu.br",
            role="COMISSAO",
            perfil_completo=True,
            is_staff=True
        )

        self.regular_user = User.objects.create_user(
            email="atleta@ufvjm.edu.br",
            role="REPRESENTANTE",
            perfil_completo=True
        )

        self.config = ConfiguracaoGeral.objects.create(nome="Config Teste", ativo=True)

    def test_permission_denied_for_regular_user(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse('agendamento_dashboard'))
        self.assertEqual(response.status_code, 302, "Usuário sem permissão de comissão deve ser redirecionado")

    def test_dashboard_view_comissao(self):
        self.client.force_login(self.comissao_user)
        response = self.client.get(reverse('agendamento_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gerador de Horários")

    def test_datas_crud_views(self):
        self.client.force_login(self.comissao_user)
        # List & Add
        response = self.client.post(reverse('agendamento_datas'), {
            'data': '2026-09-15',
            'horario_inicio': '08:00',
            'horario_fim': '20:00',
            'ativo': True
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(DataDisponivel.objects.filter(data=date(2026, 9, 15)).exists())
        d_obj = DataDisponivel.objects.get(data=date(2026, 9, 15))

        # Edit POST via modal endpoint
        edit_post = self.client.post(reverse('agendamento_data_edit', args=[d_obj.pk]), {
            'data': '2026-09-15',
            'horario_inicio': '09:00',
            'horario_fim': '21:00',
            'ativo': True
        })
        self.assertEqual(edit_post.status_code, 302)
        d_obj.refresh_from_db()
        self.assertEqual(d_obj.horario_inicio, time(9, 0))
        self.assertEqual(d_obj.horario_fim, time(21, 0))

        # Delete
        del_resp = self.client.post(reverse('agendamento_data_delete', args=[d_obj.pk]))
        self.assertEqual(del_resp.status_code, 302)
        self.assertFalse(DataDisponivel.objects.filter(data=date(2026, 9, 15)).exists())

    def test_recursos_crud_views(self):
        self.client.force_login(self.comissao_user)
        # Create
        response = self.client.post(reverse('agendamento_recursos'), {
            'nome': 'Quadra de Vôlei',
            'descricao': 'Piso de madeira',
            'ordem': 1,
            'ativo': True
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(RecursoLocal.objects.filter(nome='Quadra de Vôlei').exists())

        rec = RecursoLocal.objects.get(nome='Quadra de Vôlei')
        del_resp = self.client.post(reverse('agendamento_recurso_delete', args=[rec.pk]))
        self.assertEqual(del_resp.status_code, 302)
        self.assertFalse(RecursoLocal.objects.filter(nome='Quadra de Vôlei').exists())

    def test_gerar_e_visualizar_cenario_views(self):
        self.client.force_login(self.comissao_user)
        response = self.client.post(reverse('agendamento_gerar'), {
            'titulo': 'Cenário Teste View'
        })
        self.assertEqual(response.status_code, 302)
        cenario = CenarioExecucao.objects.filter(titulo='Cenário Teste View').first()
        self.assertIsNotNone(cenario)

        # Detalhe view
        detalhe_resp = self.client.get(reverse('agendamento_cenario_detalhe', args=[cenario.pk]))
        self.assertEqual(detalhe_resp.status_code, 200)
        self.assertContains(detalhe_resp, 'Cenário Teste View')

    def test_resetar_horarios_view(self):
        self.client.force_login(self.comissao_user)
        response = self.client.post(reverse('agendamento_resetar_horarios'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('agendamento_dashboard'))
