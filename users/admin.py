from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from users.models import User, ComissaoWhitelist, MembroDelegacao, InscritosPorDelegacao

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Personaliza a interface do Django Admin para o modelo User customizado.
    Como não usamos senhas locais, removemos os campos de senha da visualização.
    """
    model = User
    actions = ['resetar_inscricao_delegados']

    
    # Define as colunas mostradas na lista do admin
    list_display = ('email', 'nome_completo', 'role', 'get_delegacao', 'parent_delegate', 'cpf', 'perfil_completo', 'is_staff', 'date_joined')
    list_filter = ('role', 'perfil_completo', 'is_staff', 'is_superuser')
    search_fields = ('email', 'nome_completo', 'cpf', 'nome_delegacao', 'parent_delegate__nome_delegacao')
    ordering = ('email',)
    
    # Agrupa os campos na página de detalhe/edição
    fieldsets = (
        (None, {'fields': ('email', 'nome_completo', 'foto_url', 'google_id')}),
        ('Controle de Acesso (RBAC)', {'fields': ('role', 'parent_delegate', 'cpf', 'perfil_completo')}),
        ('Informações da Delegação', {'fields': (
            'nome_delegacao', 'status_delegacao', 'justificativa_delegacao',
            'link_comprovante_pagamento', 'status_pagamento', 'justificativa_pagamento'
        )}),
        ('Permissões Django', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Datas Importantes', {'fields': ('last_login', 'date_joined')}),
    )
    
    # Campos que só podem ser visualizados (readonly)
    readonly_fields = ('perfil_completo', 'google_id', 'last_login', 'date_joined')
    
    # Sobrescreve para não exigir senhas no formulário de criação
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'nome_completo', 'role', 'nome_delegacao', 'parent_delegate', 'cpf', 'is_staff', 'is_superuser'),
        }),
    )

    def get_delegacao(self, obj):
        delegacao = obj.delegacao_ativa.nome_delegacao
        if delegacao:
            if obj.parent_delegate:
                return f"{delegacao} (Membro)"
            return delegacao
        return "-"
    get_delegacao.short_description = 'Delegação'

    @admin.action(description="Resetar/Excluir inscrição e liberar representante(s)")
    def resetar_inscricao_delegados(self, request, queryset):
        count = 0
        for user in queryset:
            delegacao = user.delegacao_ativa
            if delegacao.role == 'REPRESENTANTE':
                if hasattr(delegacao, 'inscricao'):
                    delegacao.inscricao.delete()
                delegacao.status_delegacao = 'pendente'
                delegacao.save()
                count += 1
        self.message_user(request, f"{count} representante(s) teve(ram) a inscrição resetada e acesso liberado.")



@admin.register(ComissaoWhitelist)
class ComissaoWhitelistAdmin(admin.ModelAdmin):
    """
    Interface administrativa para gerenciar e-mails da Comissão autorizados previamente.
    """
    list_display = ('email', 'data_adicao')
    search_fields = ('email',)
    ordering = ('-data_adicao',)


@admin.register(MembroDelegacao)
class MembroDelegacaoAdmin(admin.ModelAdmin):
    """
    Interface administrativa para gerenciar membros autorizados por delegados.
    """
    list_display = ('email', 'delegado_principal', 'data_adicao')
    list_filter = ('delegado_principal',)
    search_fields = ('email', 'delegado_principal__email', 'delegado_principal__nome_completo')
    ordering = ('-data_adicao',)


class InscritoFilter(admin.SimpleListFilter):
    """
    Filtro personalizado para o Django Admin para filtrar representantes
    pelo status de inscrição (se já enviaram a inscrição ou não).
    """
    title = 'Status de Inscrição'
    parameter_name = 'inscrito'

    def lookups(self, request, model_admin):
        return (
            ('sim', 'Inscrito (Sim)'),
            ('nao', 'Não Inscrito (Não)'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'sim':
            return queryset.filter(inscricao__isnull=False)
        if self.value() == 'nao':
            return queryset.filter(inscricao__isnull=True)
        return queryset


@admin.register(InscritosPorDelegacao)
class InscritosPorDelegacaoAdmin(admin.ModelAdmin):
    """
    Interface administrativa para exibir o relatório de inscritos por delegação.
    Mostra o nome da delegação, a quantidade de atletas cadastrados, os campi e se estão inscritos.
    """
    list_display = ('nome_delegacao_display', 'get_atletas_count', 'get_campus', 'get_inscrito')
    list_filter = ('atletas__campus', InscritoFilter)
    search_fields = ('nome_delegacao', 'email', 'nome_completo')
    ordering = ('nome_delegacao',)

    def nome_delegacao_display(self, obj):
        return obj.nome_delegacao or obj.nome_completo or obj.email
    nome_delegacao_display.short_description = 'Nome da Delegação'
    nome_delegacao_display.admin_order_field = 'nome_delegacao'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Filtra apenas os representantes que são delegados principais
        # E exclui perfis de administração, superusuários e membros de comissão (is_staff/is_superuser)
        # Além de excluir e-mails do sistema gerenciador (admin@ufvjm.edu.br / admin@)
        qs = qs.filter(role='REPRESENTANTE', parent_delegate__isnull=True)
        qs = qs.exclude(is_superuser=True).exclude(is_staff=True)
        qs = qs.exclude(email='admin@ufvjm.edu.br').exclude(email__startswith='admin@')
        
        from django.db.models import Count
        return qs.annotate(atletas_count=Count('atletas', distinct=True)).prefetch_related('atletas__campus', 'inscricao').distinct()


    def get_atletas_count(self, obj):
        count = obj.atletas_count
        if count == 1:
            return "1 atleta"
        return f"{count} atletas"
    get_atletas_count.short_description = 'Quantidade de Atletas'
    get_atletas_count.admin_order_field = 'atletas_count'

    def get_campus(self, obj):
        # Coleta e agrupa os campi distintos dos atletas dessa delegação
        campuses = {atleta.campus.nome for atleta in obj.atletas.all() if atleta.campus}
        if campuses:
            return ", ".join(sorted(campuses))
        return "-"
    get_campus.short_description = 'Campus/Campi'

    def get_inscrito(self, obj):
        return hasattr(obj, 'inscricao')
    get_inscrito.short_description = 'Inscrito?'
    get_inscrito.boolean = True

    # Impede a criação, edição e exclusão nesta tela específica, já que é de visualização/relatório
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False



