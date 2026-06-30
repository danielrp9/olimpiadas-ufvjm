from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from users.models import User, ComissaoWhitelist, MembroDelegacao

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Personaliza a interface do Django Admin para o modelo User customizado.
    Como não usamos senhas locais, removemos os campos de senha da visualização.
    """
    model = User
    
    # Define as colunas mostradas na lista do admin
    list_display = ('email', 'nome_completo', 'role', 'parent_delegate', 'cpf', 'perfil_completo', 'is_staff', 'date_joined')
    list_filter = ('role', 'perfil_completo', 'is_staff', 'is_superuser')
    search_fields = ('email', 'nome_completo', 'cpf')
    ordering = ('email',)
    
    # Agrupa os campos na página de detalhe/edição
    fieldsets = (
        (None, {'fields': ('email', 'nome_completo', 'foto_url', 'google_id')}),
        ('Controle de Acesso (RBAC)', {'fields': ('role', 'parent_delegate', 'cpf', 'perfil_completo')}),
        ('Permissões Django', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Datas Importantes', {'fields': ('last_login', 'date_joined')}),
    )
    
    # Campos que só podem ser visualizados (readonly)
    readonly_fields = ('perfil_completo', 'google_id', 'last_login', 'date_joined')
    
    # Sobrescreve para não exigir senhas no formulário de criação
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'nome_completo', 'role', 'parent_delegate', 'cpf', 'is_staff', 'is_superuser'),
        }),
    )


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

