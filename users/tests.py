from django.test import TestCase
from django.contrib.admin.sites import AdminSite
from users.models import User, InscritosPorDelegacao
from core.models import Campus, Atleta
from users.admin import InscritosPorDelegacaoAdmin


class InscritosPorDelegacaoTestCase(TestCase):
    def setUp(self):
        # Create campuses
        self.campus_diamantina = Campus.objects.create(nome="Campus de Diamantina")
        self.campus_janauba = Campus.objects.create(nome="Campus de Janaúba")

        # Create Representative Users (Delegations)
        self.delegacao_1 = User.objects.create_user(
            email="thebug@test.com",
            nome_completo="Representante Bug",
            nome_delegacao="The Bug",
            role="REPRESENTANTE",
            perfil_completo=True
        )
        self.delegacao_2 = User.objects.create_user(
            email="outra@test.com",
            nome_completo="Outro Representante",
            nome_delegacao="Outra Delegação",
            role="REPRESENTANTE",
            perfil_completo=True
        )

        # Create a Commission user (should not appear in the queryset of InscritosPorDelegacao)
        self.comissao = User.objects.create_user(
            email="comissao@test.com",
            nome_completo="Membro Comissão",
            role="COMISSAO",
            perfil_completo=True
        )

        # Create a Sub-delegate user (should not appear in the queryset of InscritosPorDelegacao)
        self.sub_delegado = User.objects.create_user(
            email="sub@test.com",
            nome_completo="Sub Delegado",
            role="REPRESENTANTE",
            parent_delegate=self.delegacao_1,
            perfil_completo=True
        )

        # Create athletes for delegation 1
        Atleta.objects.create(
            nome_completo="Atleta Bug 1",
            email="bug1@test.com",
            matricula="12345",
            curso="Sistemas de Informação",
            campus=self.campus_diamantina,
            genero="M",
            tipo_atleta="estudante",
            cadastrado_por=self.delegacao_1
        )
        Atleta.objects.create(
            nome_completo="Atleta Bug 2",
            email="bug2@test.com",
            matricula="12346",
            curso="Sistemas de Informação",
            campus=self.campus_diamantina,
            genero="F",
            tipo_atleta="estudante",
            cadastrado_por=self.delegacao_1
        )

        # Create athletes for delegation 2 with a different campus
        Atleta.objects.create(
            nome_completo="Atleta Outra",
            email="outra1@test.com",
            matricula="67890",
            curso="Agronomia",
            campus=self.campus_janauba,
            genero="M",
            tipo_atleta="estudante",
            cadastrado_por=self.delegacao_2
        )

        # Instantiate Mock Admin site
        self.site = AdminSite()
        self.admin = InscritosPorDelegacaoAdmin(InscritosPorDelegacao, self.site)

    def test_queryset_returns_only_main_delegations(self):
        """
        Verify that the queryset only returns users with role='REPRESENTANTE'
        and parent_delegate is null.
        """
        request = None
        qs = self.admin.get_queryset(request)
        
        # Should contain delegacao_1 and delegacao_2
        # Should NOT contain comissao or sub_delegado
        self.assertEqual(qs.count(), 2)
        emails = [user.email for user in qs]
        self.assertIn("thebug@test.com", emails)
        self.assertIn("outra@test.com", emails)
        self.assertNotIn("comissao@test.com", emails)
        self.assertNotIn("sub@test.com", emails)

    def test_athlete_count_annotation(self):
        """
        Verify that the queryset correctly annotates the number of athletes.
        """
        request = None
        qs = self.admin.get_queryset(request)
        
        delegacao_1_qs = qs.get(email="thebug@test.com")
        self.assertEqual(delegacao_1_qs.atletas_count, 2)
        self.assertEqual(self.admin.get_atletas_count(delegacao_1_qs), "2 atletas")

        delegacao_2_qs = qs.get(email="outra@test.com")
        self.assertEqual(delegacao_2_qs.atletas_count, 1)
        self.assertEqual(self.admin.get_atletas_count(delegacao_2_qs), "1 atleta")

    def test_campus_retrieval(self):
        """
        Verify that get_campus method properly returns the list of campuses for delegation athletes.
        """
        request = None
        qs = self.admin.get_queryset(request)

        delegacao_1_qs = qs.get(email="thebug@test.com")
        self.assertEqual(self.admin.get_campus(delegacao_1_qs), "Campus de Diamantina")

        delegacao_2_qs = qs.get(email="outra@test.com")
        self.assertEqual(self.admin.get_campus(delegacao_2_qs), "Campus de Janaúba")

        # Test case where a delegation has no athletes
        empty_delegation = User.objects.create_user(
            email="empty@test.com",
            nome_completo="Representante Vazio",
            nome_delegacao="Sem Atletas",
            role="REPRESENTANTE",
            perfil_completo=True
        )
        empty_qs = self.admin.get_queryset(request).get(email="empty@test.com")
        self.assertEqual(self.admin.get_campus(empty_qs), "-")
        self.assertEqual(self.admin.get_atletas_count(empty_qs), "0 atletas")

    def test_admin_and_staff_exclusion(self):
        """
        Verify that admin (superuser) and staff users are not returned.
        """
        # Create a superuser/admin user
        admin_user = User.objects.create_superuser(
            email="admin@test.com",
            password="password123"
        )
        # Create a staff representative (force is_staff to True via update)
        staff_rep = User.objects.create_user(
            email="staff_rep@test.com",
            nome_completo="Staff Rep",
            role="REPRESENTANTE",
            perfil_completo=True
        )
        User.objects.filter(pk=staff_rep.pk).update(is_staff=True)

        request = None
        qs = self.admin.get_queryset(request)
        emails = [user.email for user in qs]

        self.assertNotIn("admin@test.com", emails)
        self.assertNotIn("staff_rep@test.com", emails)

    def test_enrollment_status_and_filter(self):
        """
        Verify that get_inscrito works and InscritoFilter filters correctly.
        """
        from core.models import Inscricao
        from users.admin import InscritoFilter

        # At first, both delegations have no Inscricao
        request = None
        qs = self.admin.get_queryset(request)
        delegacao_1_qs = qs.get(email="thebug@test.com")
        delegacao_2_qs = qs.get(email="outra@test.com")

        self.assertFalse(self.admin.get_inscrito(delegacao_1_qs))
        self.assertFalse(self.admin.get_inscrito(delegacao_2_qs))

        # Create Inscricao for delegation 1
        Inscricao.objects.create(
            delegacao=self.delegacao_1,
            status="pendente"
        )

        # Refresh queryset
        qs = self.admin.get_queryset(request)

        delegacao_1_qs = qs.get(email="thebug@test.com")
        delegacao_2_qs = qs.get(email="outra@test.com")

        self.assertTrue(self.admin.get_inscrito(delegacao_1_qs))
        self.assertFalse(self.admin.get_inscrito(delegacao_2_qs))

        # Test filter queryset
        # Filter for registered ('sim')
        f_sim = InscritoFilter(None, {'inscrito': ['sim']}, InscritosPorDelegacao, self.admin)
        qs_sim = f_sim.queryset(None, qs)
        self.assertEqual(qs_sim.count(), 1)
        self.assertEqual(qs_sim.first().email, "thebug@test.com")

        # Filter for not registered ('nao')
        f_nao = InscritoFilter(None, {'inscrito': ['nao']}, InscritosPorDelegacao, self.admin)
        qs_nao = f_nao.queryset(None, qs)
        self.assertNotIn("thebug@test.com", [u.email for u in qs_nao])
        self.assertIn("outra@test.com", [u.email for u in qs_nao])



