from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from core.models import Inscricao

class Command(BaseCommand):
    help = 'Remove a inscrição de um representante/delegação pelo e-mail do usuário para liberar re-inscrição.'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='E-mail do representante da delegação')

    def handle(self, *args, **options):
        email = options['email']
        User = get_user_model()

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise CommandError(f'Usuário com e-mail "{email}" não foi encontrado.')

        delegacao = user.delegacao_ativa

        if delegacao.role != 'REPRESENTANTE':
            raise CommandError(f'O usuário "{email}" não é um Representante de Delegação.')

        has_inscricao = hasattr(delegacao, 'inscricao')

        if not has_inscricao:
            self.stdout.write(self.style.WARNING(
                f'A delegação "{delegacao.nome_delegacao or email}" não possui nenhuma inscrição enviada.'
            ))
        else:
            inscricao = delegacao.inscricao
            inscricao.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Inscrição da delegação "{delegacao.nome_delegacao or email}" removida com sucesso.'
            ))

        # Sempre redefine o status para pendente para garantir que o acesso está liberado
        delegacao.status_delegacao = 'pendente'
        delegacao.save()
        self.stdout.write(self.style.SUCCESS(
            f'Status da delegação "{delegacao.nome_delegacao or email}" resetado para "Pendente de Análise".'
        ))
