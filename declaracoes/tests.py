import json
import zipfile
import io
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.models import Campus, Atleta
from .models import MembroComissao, HistoricoEmissao
from .services import (
    gerar_pdf_declaracao_bytes,
    iniciar_geracao_assincrona,
    get_task_progress,
    update_task_progress
)

User = get_user_model()


class DeclaracoesTestCase(TestCase):
    def setUp(self):
        self.campus1, _ = Campus.objects.get_or_create(nome="Campus Diamantina")
        self.campus2, _ = Campus.objects.get_or_create(nome="Campus Mucuri")

        self.user_comissao = User.objects.create(
            email="admin_comissao@ufvjm.edu.br",
            nome_completo="Admin Comissao",
            role="COMISSAO",
            perfil_completo=True,
            is_staff=True
        )

        self.atleta1 = Atleta.objects.create(
            nome_completo="Atleta Deferido Um",
            matricula="2021001",
            email="atleta1@ufvjm.edu.br",
            curso="Educação Física",
            campus=self.campus1,
            cadastrado_por=self.user_comissao,
            status_avaliacao="deferido"
        )

        self.atleta2 = Atleta.objects.create(
            nome_completo="Atleta Deferido Dois",
            matricula="2021002",
            email="atleta2@ufvjm.edu.br",
            curso="Sistemas de Informação",
            campus=self.campus2,
            cadastrado_por=self.user_comissao,
            status_avaliacao="deferido"
        )

        self.atleta_indeferido = Atleta.objects.create(
            nome_completo="Atleta Nao Deferido",
            matricula="2021003",
            email="atleta3@ufvjm.edu.br",
            curso="Medicina",
            campus=self.campus1,
            cadastrado_por=self.user_comissao,
            status_avaliacao="indeferido"
        )

        self.membro_comissao = MembroComissao.objects.create(
            nome_completo="Daniel Rodrigues Pereira",
            matricula="20212016010",
            cargo="Organizador",
            email="daniel.pereira@ufvjm.edu.br",
            ativo=True
        )

        self.client = Client()
        self.client.force_login(self.user_comissao)

    def test_gerar_pdf_declaracao_individual(self):
        """Testa geração de bytes do PDF com sobreposição no template oficial"""
        pdf_bytes = gerar_pdf_declaracao_bytes(
            nome="Daniel Rodrigues Pereira",
            matricula="20212016010",
            papel="Organizador",
            horas=100,
            periodo="27 de setembro a 25 de outubro de 2025",
            cidade_data="Diamantina, 23 de abril de 2026"
        )
        self.assertIsNotNone(pdf_bytes)
        self.assertTrue(len(pdf_bytes) > 50000)  # O PDF oficial com logo tem mais de 80KB

    def test_previa_declaracao_view(self):
        """Testa o endpoint de prévia de declaração"""
        url = reverse('declaracoes_previa')
        response = self.client.get(url, {'tipo': 'atleta', 'horas': 60})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_iniciar_geracao_atletas(self):
        """Testa o disparo da geração assíncrona de atletas deferidos"""
        url = reverse('declaracoes_iniciar')
        payload = {
            'tipo': 'atleta',
            'horas': 60,
            'periodo': '27 de setembro a 25 de outubro de 2025',
            'cidade_data': 'Diamantina, 23 de abril de 2026',
            'campis': [str(self.campus1.id), str(self.campus2.id)]
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('task_id', data)

        task_id = data['task_id']
        progress = get_task_progress(task_id)
        self.assertIsNotNone(progress)

    def test_apenas_atletas_deferidos_sao_considerados(self):
        """Garante que atletas indeferidos não são incluídos na geração"""
        task_id = iniciar_geracao_assincrona(
            tipo='atleta',
            selecionados_ids=None,
            horas=60,
            periodo='27 de setembro a 25 de outubro de 2025',
            cidade_data='Diamantina, 23 de abril de 2026',
            campis_ids=[str(self.campus1.id)],
            solicitado_por=self.user_comissao
        )
        progress = get_task_progress(task_id)
        # Apenas atleta1 está deferido no campus1 (atleta_indeferido não deve entrar)
        self.assertEqual(progress['total'], 1)
